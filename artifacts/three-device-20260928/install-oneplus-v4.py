"""One-shot controller operation; requires the explicitly approved idle window."""

import json
import os
import re
import subprocess
import sys
import time
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PRIVATE = Path.home() / "CloudCtlExternal/acceptance/20260928-v4"
APK = PRIVATE / "cloudctl-business-acceptance-v4.apk"
RUN = PRIVATE / "install-window"
SERIAL = "b0644fb5"
PACKAGE = "com.company.cloudctl.companion"
JAVA = Path.home() / "CloudCtlExternal/jdks/temurin-17/Contents/Home"
TOOLS = Path.home() / "CloudCtlExternal/android-sdk/build-tools/35.0.0"
EXPECTED_APK = "cff3b03a72f56781a73d2713bd68a968f1d47a6c21f27c528629f72f6e9fcf70"
EXPECTED_OLD = "c6a39272612bf507c70d0a5f3084162b87770d445fcecedb4e659be5cd4a9005"
EXPECTED_SIGNER = "67a6d9af9e400326e1254b87ea310f34b1a1395664ca89424f141dbabba57796"
SETTINGS = (
    "enabled_accessibility_services",
    "accessibility_enabled",
    "enabled_notification_listeners",
    "default_input_method",
)


def execute(args, *, timeout=30, input_text=None):
    result = subprocess.run(  # noqa: S603 - controller-owned fixed argv, never a shell
        [str(arg) for arg in args],
        cwd=REPO,
        text=True,
        input=input_text,
        capture_output=True,
        timeout=timeout,
        env={**os.environ, "JAVA_HOME": str(JAVA)},
    )
    if result.returncode:
        raise RuntimeError(f"Command {args[0]} exited {result.returncode}")
    return result.stdout.strip()


def adb(*args, timeout=20):
    return execute(["adb", "-s", SERIAL, *args], timeout=timeout)


def save(name, value):
    (RUN / name).write_text(json.dumps(value, indent=2, default=str) + "\n")


def cloud(action):
    payload = execute(
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=10",
            "seoul",
            "/home/ubuntu/cloudctl-mobile/releases/order-delivery-557f547/.venv/bin/python",
            "-",
            action,
        ],
        timeout=75,
        input_text=Path(__file__).with_name("oneplus-v4-cloud.py").read_text(),
    )
    return json.loads(payload)


def signer(path):
    result = execute([TOOLS / "apksigner", "verify", "--print-certs", path])
    certificates = re.findall(r"certificate SHA-256 digest: ([a-f0-9]{64})", result)
    assert certificates == [EXPECTED_SIGNER], "APK signer mismatch"


def package_snapshot():
    raw = adb("shell", "dumpsys", "package", PACKAGE)
    version = re.search(r"^\s+versionCode=(\d+)", raw, re.MULTILINE)
    name = re.search(r"^\s+versionName=(\S+)", raw, re.MULTILINE)
    first = re.findall(r"^\s+firstInstallTime=(.+)$", raw, re.MULTILINE)
    uid = re.search(r"^\s+appId=(\d+)", raw, re.MULTILINE)
    grants = re.findall(r"^\s+(\S+): granted=(true|false)(.*)$", raw, re.MULTILINE)
    assert version and name and uid and first and grants
    return {
        "versionCode": int(version.group(1)),
        "versionName": name.group(1),
        "firstInstallTime": first,
        "appId": uid.group(1),
        "grants": grants,
        "settings": {key: adb("shell", "settings", "get", "secure", key) for key in SETTINGS},
    }


def pull_installed(filename):
    paths = adb("shell", "pm", "path", PACKAGE).splitlines()
    assert len(paths) == 1 and paths[0].startswith("package:/data/app/")
    path = paths[0].removeprefix("package:")
    assert path.endswith("/base.apk")
    destination = RUN / filename
    adb("pull", path, str(destination), timeout=60)
    signer(destination)
    return sha256(destination.read_bytes()).hexdigest()


def report(stage, value):
    print(json.dumps({"stage": stage, **value}, default=str), flush=True)


def main():
    assert sys.argv[1:] == ["--approved-idle-window"], "Explicit authorized window required"
    os.umask(0o077)
    RUN.mkdir(mode=0o700)
    assert sha256(APK.read_bytes()).hexdigest() == EXPECTED_APK
    signer(APK)
    assert adb("get-state") == "device"
    assert adb("shell", "getprop", "ro.product.model") == "LE2100"
    assert adb("shell", "am", "get-current-user") == "0"
    metadata = execute([TOOLS / "aapt", "dump", "badging", APK])
    assert f"package: name='{PACKAGE}' versionCode='4'" in metadata
    assert "versionName='0.1.0-business-acceptance.4'" in metadata

    lock_args = [sys.executable, REPO / "scripts/device_lock.py"]
    assert json.loads(execute([*lock_args, "status", SERIAL]))["state"] == "FREE"
    lock = json.loads(
        execute(
            [
                *lock_args,
                "acquire",
                SERIAL,
                "--holder",
                "controller-v4-20260928",
                "--purpose",
                "Authorized data-preserving OnePlus v4 update",
                "--task-id",
                "three-device-stage2-oneplus-v4",
                "--ttl",
                "1800",
            ]
        )
    )
    save("lock-private.json", lock)
    fencing = lock["fencing"]
    report("lock-acquired", {"serial": SERIAL, "fencing": fencing})
    attempted_prepare = False
    try:
        before = package_snapshot()
        save("package-before-private.json", before)
        assert before["versionCode"] == 3
        assert before["versionName"] == "0.1.0-business-acceptance.3"
        assert pull_installed("installed-before-v3.apk") == EXPECTED_OLD
        attempted_prepare = True
        prepared = cloud("prepare")
        save("cloud-maintenance.json", prepared)
        report("maintenance", prepared)
        assert prepared["device"]["maintenance"]
        checked = cloud("verify")
        assert checked["device"]["maintenance"] and checked["idle"]
        started = datetime.now(UTC).isoformat()
        result = adb("install", "-r", str(APK), timeout=180)
        assert "Success" in result.splitlines(), "Installer did not confirm success"
        finished = datetime.now(UTC).isoformat()
        after = package_snapshot()
        save("package-after-private.json", after)
        assert after["versionCode"] == 4
        assert after["versionName"] == "0.1.0-business-acceptance.4"
        for key in ("firstInstallTime", "appId", "grants", "settings"):
            assert after[key] == before[key], f"Unexpected change: {key}"
        assert pull_installed("installed-after-v4.apk") == EXPECTED_APK
        summary = {
            "installed": True,
            "serial": SERIAL,
            "package": PACKAGE,
            "startedAt": started,
            "finishedAt": finished,
            "versionCode": 4,
            "versionName": after["versionName"],
            "apkSha256": EXPECTED_APK,
            "signatureUnchanged": True,
            "grantEntriesUnchanged": len(after["grants"]),
            "settingsUnchanged": len(SETTINGS),
            "firstInstallTimeUnchanged": True,
            "appIdUnchanged": True,
            "privateDatabaseReread": False,
            "deviceLockFencing": fencing,
            "manualLaunch": False,
        }
        save("install-summary.json", summary)
        report("installed", summary)
        fresh = None
        for attempt in range(7):
            current = cloud("verify")
            save("cloud-post.json", current)
            seen = current["device"]["last_seen_at"]
            if (
                current["capabilities"]["companionVersion"] == after["versionName"]
                and seen is not None
                and datetime.fromisoformat(seen) >= datetime.fromisoformat(started)
            ):
                fresh = current
                break
            if attempt < 6:
                time.sleep(10)
        report("heartbeat", fresh or {"freshV4Heartbeat": False})
    finally:
        try:
            if attempted_prepare:
                finished_cloud = cloud("finish")
                save("cloud-finished.json", finished_cloud)
                report("maintenance-finished", finished_cloud)
        finally:
            released = json.loads(
                execute(
                    [*lock_args, "release", SERIAL, "--fencing", str(fencing), "--token-stdin"],
                    input_text=lock["owner_token"] + "\n",
                )
            )
            save("lock-released.json", released)
            report("lock-released", released)


if __name__ == "__main__":
    main()
