"""Web-only release with a verified backup, atomic switch and automatic rollback."""

import asyncio
import fcntl
import hashlib
import importlib.util
import json
import os
import re
import signal
import sys
import tarfile
import time
from pathlib import Path

import httpx

ROOT = Path("/home/ubuntu/cloudctl-mobile")
OLD_API = ROOT / "releases/order-delivery-557f547"
OLD_WEB = Path("/var/www/cloudctl-mobile-web-qa-097d4ac68088")


def load_operations():
    path = ROOT / "incoming/listing-sync-b3bd1f3/cloudctl-listing-sync-deploy-20260926.py"
    spec = importlib.util.spec_from_file_location("web_release_operations", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def service_state(ops):
    result = ops.run(
        [
            "systemctl",
            "show",
            ops.SERVICE,
            "-p",
            "ActiveState",
            "-p",
            "MainPID",
            "-p",
            "WorkingDirectory",
        ],
        capture_output=True,
        text=True,
    )
    values = dict(line.split("=", 1) for line in result.stdout.splitlines())
    assert values["ActiveState"] == "active"
    assert values["WorkingDirectory"] == str(OLD_API)
    return values


def switch_web(ops, target, sha):
    pending = ops.WEB.with_name(f".cloudctl-web-{sha}.next")
    assert not pending.exists() and not pending.is_symlink()
    ops.run(["sudo", "-n", "ln", "-s", str(target), str(pending)])
    ops.run(["sudo", "-n", "mv", "-Tf", str(pending), str(ops.WEB)])
    assert ops.WEB.resolve() == target


def verify_http(prior, web, credential, source_sha=None):
    ops = prior.ops
    routes = (
        "/cloudctl-mobile/",
        "/cloudctl-mobile/im",
        "/cloudctl-mobile/orders",
        "/cloudctl-mobile/fleet",
        "/cloudctl-mobile/operations/product-management/product-management-01",
    )
    with httpx.Client(timeout=20, trust_env=False) as client:
        for path in ("/health/live", "/health/ready"):
            client.get(ops.HOST + path).raise_for_status()
        for path in routes:
            assert client.get(ops.HOST + path).status_code == 401
            response = client.get(ops.HOST + path, auth=credential)
            response.raise_for_status()
            assert response.content == (web / "index.html").read_bytes()
        assets = prior.Assets()
        assets.feed((web / "index.html").read_text())
        assert assets.urls
        for url in assets.urls:
            assert url.startswith("/cloudctl-mobile/assets/")
            response = client.get(ops.HOST + url, auth=credential)
            response.raise_for_status()
            assert response.content == (web / "assets" / Path(url).name).read_bytes()
        for path in (
            "/api/v1/session",
            "/api/v1/devices",
            "/api/v1/products",
            "/api/v1/orders",
            "/api/v1/im/threads",
        ):
            assert client.get(ops.HOST + path).status_code == 401
            client.get(ops.HOST + path, auth=credential).raise_for_status()
        if source_sha:
            response = client.get(ops.HOST + "/cloudctl-mobile/version.json", auth=credential)
            response.raise_for_status()
            assert response.json()["sourceSha"] == source_sha
            assert response.content == (web / "version.json").read_bytes()
    prior.verify_notification_config(credential)
    return {"routes": len(routes), "entryAssets": len(assets.urls), "apiReads": 5}


async def business_state(ops):
    connection = await ops.database()
    try:
        return {
            "schema": await connection.fetchval("SELECT version_num FROM alembic_version"),
            "outCount": await connection.fetchval(
                "SELECT count(*) FROM im_message WHERE direction='OUT'"
            ),
            "taskCount": await connection.fetchval("SELECT count(*) FROM mobile_task"),
        }
    finally:
        await connection.close()


async def main():
    os.umask(0o077)
    source_sha, archive_hash = sys.argv[1:]
    assert re.fullmatch(r"[a-f0-9]{40}", source_sha)
    assert re.fullmatch(r"[a-f0-9]{64}", archive_hash)
    short_sha = source_sha[:12]
    name = f"web-qa-{short_sha}"
    incoming = ROOT / "incoming" / name
    archive_path = incoming / "web.tar.gz"
    destination = Path("/var/www") / f"cloudctl-mobile-{name}"
    backup_path = ROOT / "backups" / name
    verification_db = f"cloudctl_web_verify_{short_sha}"
    prior = load_operations()
    ops = prior.ops
    assert digest(archive_path) == archive_hash
    assert not destination.exists() and not backup_path.exists()
    with tarfile.open(archive_path) as archive:
        for member in archive.getmembers():
            path = Path(member.name)
            assert not path.is_absolute() and ".." not in path.parts
            assert member.isfile() or member.isdir()
        version = json.load(archive.extractfile("./version.json"))
        assert version["sourceSha"] == source_sha
        assert version["mockEnabled"] is False
        assert version["devAuthEnabled"] is False

    with (ROOT / ".deploy.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert ops.WEB.is_symlink() and ops.WEB.resolve() == OLD_WEB
        before_service = service_state(ops)
        credential = ops.auth()
        verify_http(prior, OLD_WEB, credential)
        before_business = await business_state(ops)
        assert before_business["schema"] == "20260926_0035"
        await prior.verified_backup(backup_path, str(OLD_WEB), verification_db)
        manifest = json.loads((backup_path / "manifest.json").read_text())
        assert manifest["restoreVerified"]
        ops.run(prior.backup.PG + ["dropdb", "-U", "cloudctl", verification_db])

        ops.run(["sudo", "-n", "install", "-d", "-m", "755", str(destination)])
        ops.run(["sudo", "-n", "tar", "-xzf", str(archive_path), "-C", str(destination)])
        # Retain hashed assets used by already-open pages and lazy-loaded chunks.
        old_assets = list((OLD_WEB / "assets").rglob("*"))
        for old in old_assets:
            if old.is_file():
                candidate = destination / "assets" / old.relative_to(OLD_WEB / "assets")
                assert not candidate.exists() or digest(candidate) == digest(old)
        ops.run(
            ["sudo", "-n", "cp", "-an", str(OLD_WEB / "assets") + "/.", str(destination / "assets")]
        )
        ops.run(["sudo", "-n", "chown", "-R", "root:www-data", str(destination)])
        ops.run(["sudo", "-n", "chmod", "-R", "a+rX", str(destination)])
        assert service_state(ops) == before_service
        assert ops.WEB.resolve() == OLD_WEB

        switched = False
        try:
            switched = True
            switch_web(ops, destination, short_sha)
            verified = verify_http(prior, destination, credential, source_sha)
            assert service_state(ops) == before_service
            after_business = await business_state(ops)
            assert after_business["schema"] == before_business["schema"]
            result = {
                "activated": True,
                "release": name,
                "sourceSha": source_sha,
                "archiveSha256": archive_hash,
                "activatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "oldWeb": str(OLD_WEB),
                "newWeb": str(destination),
                "apiRelease": str(OLD_API),
                "apiPid": before_service["MainPID"],
                "apiRestarted": False,
                "databaseMigrated": False,
                "backupRestoreVerified": True,
                "backupTables": manifest["tableCount"],
                "businessBefore": before_business,
                "businessAfter": after_business,
                "receiveOnly": True,
                "imMode": "NOTIFICATION",
                "deviceActionsIssued": False,
                "httpVerification": verified,
                "retainedOldAssetFiles": sum(path.is_file() for path in old_assets),
            }
            (backup_path / "activation-result.json").write_text(json.dumps(result, indent=2) + "\n")
            print(json.dumps(result), flush=True)
        except BaseException:
            rollback_verified = False
            try:
                if switched and ops.WEB.resolve() != OLD_WEB:
                    assert ops.WEB.resolve() == destination
                    switch_web(ops, OLD_WEB, short_sha + "-rollback")
                verify_http(prior, OLD_WEB, credential)
                assert service_state(ops) == before_service
                rollback_verified = True
            finally:
                (backup_path / "rollback-result.json").write_text(
                    json.dumps({"rollbackVerified": rollback_verified}) + "\n"
                )
            raise


if __name__ == "__main__":

    def terminate(signum, frame):
        raise KeyboardInterrupt()

    for sig in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, terminate)
    try:
        asyncio.run(main())
    except BaseException as error:
        print(json.dumps({"status": "FAILED", "errorType": type(error).__name__}), flush=True)
        raise SystemExit(1) from None
