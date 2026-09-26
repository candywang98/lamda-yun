"""Focused additive order-delivery release. No device tasks or external actions."""

import asyncio
import fcntl
import hashlib
import importlib.util
import json
import os
import re
import shutil
import signal
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import httpx


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ROOT = Path("/home/ubuntu/cloudctl-mobile")
prior = load(
    "listing_release",
    ROOT / "incoming/listing-sync-b3bd1f3/cloudctl-listing-sync-deploy-20260926.py",
)
ops, backup = prior.ops, prior.backup
OLD = ROOT / "releases/listing-sync-b3bd1f3"
OLD_WEB = "/var/www/cloudctl-mobile-listing-sync-b3bd1f3"
OLD_SCHEMA, NEW_SCHEMA = "20260926_0034", "20260926_0035"


def preserve_tables(before, after):
    assert set(after) == set(before) | {"order_delivery_receipt", "order_delivery_projection"}
    assert after["order_delivery_receipt"]["count"] == 0
    assert after["order_delivery_projection"]["count"] == 0
    for name, digest in before.items():
        if name != "alembic_version":
            assert after[name] == digest, f"Business table changed: {name}"


def verify_unit(path):
    assert ops.service_directory() == str(path)
    command = ops.run(
        ["systemctl", "show", ops.SERVICE, "-p", "ExecStart", "--value"],
        capture_output=True,
        text=True,
    ).stdout
    assert f"{path}/.venv/bin/python" in command


def rollback(dropin, stopped, web_switched, credential):
    failures = []
    try:
        if stopped:
            ops.run(["sudo", "-n", "systemctl", "stop", ops.SERVICE])
            if dropin.exists():
                ops.run(["sudo", "-n", "mv", str(dropin), str(dropin) + ".rolled-back"])
            ops.run(["sudo", "-n", "systemctl", "daemon-reload"])
            verify_unit(OLD)
            # Keep the additive schema and all received data; never restore an
            # old dump or drop receipts as part of an application rollback.
            ops.run(["sudo", "-n", "systemctl", "start", ops.SERVICE])
        if web_switched:
            ops.run(["sudo", "-n", "ln", "-sfn", OLD_WEB, str(ops.WEB)])
        verify_unit(OLD)
        assert ops.health()
        assert str(ops.WEB.resolve()) == OLD_WEB
        prior.verify_notification_config(credential)
    except BaseException as exc:
        failures.append(type(exc).__name__)
    return failures


async def main():
    os.umask(0o077)
    sha, source_hash, web_hash = sys.argv[1:]
    assert re.fullmatch(r"[a-f0-9]{7,40}", sha)
    assert all(re.fullmatch(r"[a-f0-9]{64}", h) for h in (source_hash, web_hash))
    name = f"order-delivery-{sha}"
    incoming = ROOT / "incoming" / name
    release = ROOT / "releases" / name
    dest = ROOT / "backups" / name
    web_new = Path("/var/www") / f"cloudctl-mobile-{name}"
    dropin = Path(
        "/etc/systemd/system/cloudctl-mobile-api.service.d/99-zzzzzzzzzzzzzz-order-delivery.conf"
    )
    db = f"cloudctl_order_verify_{sha}"
    # This is a single serialized deployment, not an async request handler.
    assert not release.exists() and not web_new.exists() and not dropin.exists()  # noqa: ASYNC240
    for filename, digest in (("source.tar.gz", source_hash), ("web.tar.gz", web_hash)):
        assert hashlib.sha256((incoming / filename).read_bytes()).hexdigest() == digest

    with (ROOT / ".deploy.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        verify_unit(OLD)
        assert str(ops.WEB.resolve()) == OLD_WEB
        connection = await ops.database()
        try:
            await ops.idle(connection)
            assert (
                await connection.fetchval("SELECT version_num FROM alembic_version") == OLD_SCHEMA
            )
        finally:
            await connection.close()
        await prior.verified_backup(dest, OLD_WEB, db)
        manifest = json.loads((dest / "manifest.json").read_text())
        assert manifest["restoreVerified"]

        release.mkdir()
        ops.run(["tar", "-xzf", str(incoming / "source.tar.gz"), "-C", str(release)])
        ops.run(["python3", "-m", "venv", "--copies", str(release / ".venv")])
        packages = release / ".venv/lib/python3.12/site-packages"
        shutil.copytree(
            (OLD / ".venv/lib/python3.12/site-packages").resolve(), packages, dirs_exist_ok=True
        )
        editable = packages / "_editable_impl_cloudctl.pth"
        editable.write_text(editable.read_text().replace(str(OLD), str(release)))
        python = str(release / ".venv/bin/python")
        ops.run(
            [
                python,
                "-c",
                "import cloudctl_api.order_delivery; "
                f"assert cloudctl_api.order_delivery.__file__.startswith({str(release)!r})",
            ],
            cwd=release,
        )
        values = ops.environment()
        values["CLOUDCTL_DATABASE_URL"] = urlunsplit(
            urlsplit(values["CLOUDCTL_DATABASE_URL"])._replace(path=f"/{db}")
        )
        values["CLOUDCTL_IM_CLASSIFIER_ENABLED"] = "false"
        migration = [python, "-m", "alembic", "-c", "services/control-api/alembic.ini"]
        for action, target in (
            ("upgrade", NEW_SCHEMA),
            ("downgrade", OLD_SCHEMA),
            ("upgrade", NEW_SCHEMA),
        ):
            ops.run(migration + [action, target], cwd=release, env=values)
            connection = await ops.database(values)
            try:
                assert (
                    await connection.fetchval("SELECT version_num FROM alembic_version") == target
                )
                actual = await backup.digest(connection)
                if target == NEW_SCHEMA:
                    preserve_tables(manifest["tables"], actual)
                else:
                    assert actual == manifest["tables"]
            finally:
                await connection.close()
        print(json.dumps({"migrationRehearsal": "PASS", "historyPreserved": True}), flush=True)
        ops.run(backup.PG + ["dropdb", "-U", "cloudctl", db])
        ops.run(["sudo", "-n", "install", "-d", "-m", "755", str(web_new)])
        ops.run(["sudo", "-n", "tar", "-xzf", str(incoming / "web.tar.gz"), "-C", str(web_new)])
        ops.run(["sudo", "-n", "chown", "-R", "root:www-data", str(web_new)])
        ops.run(["sudo", "-n", "chmod", "-R", "a+rX", str(web_new)])

        credential = ops.auth()
        prior.verify_notification_config(credential)
        connection = await ops.database()
        try:
            await ops.idle(connection)
            messages_before = await ops.message_digests(connection)
            out_count = await connection.fetchval(
                "SELECT count(*) FROM im_message WHERE direction='OUT'"
            )
            task_count = await connection.fetchval("SELECT count(*) FROM mobile_task")
        finally:
            await connection.close()
        unit = dest / "order-delivery.conf"
        unit.write_text(
            f"[Service]\nWorkingDirectory={release}\nExecStart=\n"
            f"ExecStart={python} -m uvicorn cloudctl_api.app:app "
            "--host 127.0.0.1 --port 8000 --workers 1 --proxy-headers "
            "--forwarded-allow-ips=127.0.0.1\n"
        )
        stopped = web_switched = False
        try:
            verify_unit(OLD)
            assert str(ops.WEB.resolve()) == OLD_WEB
            stopped = True
            ops.run(["sudo", "-n", "systemctl", "stop", ops.SERVICE])
            state = ops.run(
                ["systemctl", "show", ops.SERVICE, "-p", "ActiveState", "--value"],
                capture_output=True,
                text=True,
            ).stdout.strip()
            assert state == "inactive"
            connection = await ops.database()
            try:
                await ops.idle(connection)
                assert await connection.fetchval("SELECT count(*) FROM mobile_task") == task_count
                before_migration = await backup.digest(connection)
            finally:
                await connection.close()
            ops.run(migration + ["upgrade", NEW_SCHEMA], cwd=release, env=ops.environment())
            connection = await ops.database()
            try:
                assert (
                    await connection.fetchval("SELECT version_num FROM alembic_version")
                    == NEW_SCHEMA
                )
                preserve_tables(before_migration, await backup.digest(connection))
            finally:
                await connection.close()
            ops.run(["sudo", "-n", "install", "-m", "644", str(unit), str(dropin)])
            ops.run(["sudo", "-n", "systemctl", "daemon-reload"])
            verify_unit(release)
            ops.run(["sudo", "-n", "systemctl", "start", ops.SERVICE])
            assert ops.health()
            prior.verify_notification_config(credential)

            async with httpx.AsyncClient(timeout=15, trust_env=False) as client:
                for path in (
                    "/api/v1/fleet/orders/history",
                    "/api/v1/fleet/listings/history",
                    "/api/v1/orders",
                    "/api/v1/im/threads",
                ):
                    assert (await client.get(ops.HOST + path)).status_code == 401
                    (await client.get(ops.HOST + path, auth=credential)).raise_for_status()
                # Authentication-only probe: never create or dispatch a task.
                probe = await client.post(
                    ops.HOST + "/companion/v2/orders/delivery", auth=credential, json={}
                )
                assert probe.status_code in (401, 403)
            web_switched = True
            ops.run(["sudo", "-n", "ln", "-sfn", str(web_new), str(ops.WEB)])
            async with httpx.AsyncClient(timeout=15, trust_env=False) as client:
                response = await client.get(ops.HOST + "/cloudctl-mobile/", auth=credential)
                response.raise_for_status()
                assert response.content == (web_new / "index.html").read_bytes()
                assets = prior.Assets()
                assets.feed(response.text)
                assert assets.urls
                for url in assets.urls:
                    assert url.startswith("/cloudctl-mobile/assets/")
                    downloaded = await client.get(ops.HOST + url, auth=credential)
                    downloaded.raise_for_status()
                    assert downloaded.content == (web_new / "assets" / Path(url).name).read_bytes()
            connection = await ops.database()
            try:
                after = await ops.message_digests(connection)
                assert all(after.get(key) == value for key, value in messages_before.items())
                assert (
                    await connection.fetchval(
                        "SELECT count(*) FROM im_message WHERE direction='OUT'"
                    )
                    == out_count
                )
                assert await connection.fetchval("SELECT count(*) FROM mobile_task") == task_count
                assert await connection.fetchval("SELECT count(*) FROM order_delivery_receipt") == 0
                await ops.idle(connection)
            finally:
                await connection.close()
            result = {
                "activated": True,
                "release": name,
                "sourceSha": sha,
                "activatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "schema": NEW_SCHEMA,
                "backupRestoreVerified": True,
                "migrationRehearsal": "upgrade-downgrade-upgrade",
                "productionBusinessTablesPreserved": len(before_migration) - 1,
                "admissionsStoppedDuringSwitch": True,
                "receiveOnly": True,
                "imMode": "NOTIFICATION",
                "originalMessagesUnchanged": len(messages_before),
                "outCount": out_count,
                "taskCount": task_count,
                "webAssetsVerified": len(assets.urls),
                "browserVisualVerified": False,
                "androidInstalled": False,
                "realCollectionDispatched": False,
                "adbDisconnectedAcceptance": False,
                "receiptCount": 0,
                "oldApi": str(OLD),
                "oldWeb": OLD_WEB,
                "dropIn": str(dropin),
            }
            (dest / "activation-result.json").write_text(json.dumps(result, indent=2) + "\n")
            print(json.dumps(result), flush=True)
        except BaseException:
            failures = rollback(dropin, stopped, web_switched, credential)
            (dest / "rollback-result.json").write_text(
                json.dumps(
                    {
                        "rollbackVerified": not failures,
                        "errors": failures,
                        "schemaAndBusinessDataRetained": True,
                    }
                )
                + "\n"
            )
            raise


if __name__ == "__main__":

    def terminate(signum, frame):
        raise KeyboardInterrupt()

    for sig in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, terminate)
    try:
        asyncio.run(main())
    except BaseException as exc:
        print(json.dumps({"status": "FAILED", "errorType": type(exc).__name__}), flush=True)
        raise SystemExit(1) from None
