"""Controller-only normal launch after the v4 maintenance window."""

import importlib.util
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "approved_v4_install", Path(__file__).with_name("install-oneplus-v4.py")
)
assert spec is not None and spec.loader is not None
operation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(operation)


def main():
    assert sys.argv[1:] == ["--approved-idle-window"]
    os.umask(0o077)
    lock_args = [sys.executable, operation.REPO / "scripts/device_lock.py"]
    assert (
        json.loads(operation.execute([*lock_args, "status", operation.SERIAL]))["state"] == "FREE"
    )
    lock = json.loads(
        operation.execute(
            [
                *lock_args,
                "acquire",
                operation.SERIAL,
                "--holder",
                "controller-v4-recovery-20260928",
                "--purpose",
                "Normal launch after maintenance-409 stopped sync service",
                "--task-id",
                "three-device-stage2-oneplus-v4-recovery",
                "--ttl",
                "1800",
            ]
        )
    )
    operation.save("recovery-lock-private.json", lock)
    try:
        before = operation.cloud("verify")
        assert before["idle"] and not before["device"]["maintenance"]
        package = operation.package_snapshot()
        assert package["versionCode"] == 4
        started = datetime.now(UTC).isoformat()
        launch = operation.adb(
            "shell", "am", "start", "-W", "-n", operation.PACKAGE + "/.MainActivity"
        )
        assert "Status: ok" in launch
        operation.report("normal-launch", {"startedAt": started, "fencing": lock["fencing"]})
        observations = []
        fresh_seen = set()
        for attempt in range(9):
            current = operation.cloud("verify")
            observations.append(current)
            operation.save("recovery-observations.json", observations)
            seen = current["device"]["last_seen_at"]
            if seen and datetime.fromisoformat(seen) >= datetime.fromisoformat(started):
                fresh_seen.add(seen)
            if len(fresh_seen) >= 3:
                break
            if attempt < 8:
                time.sleep(10)
        summary = {
            "manualLaunch": True,
            "fencing": lock["fencing"],
            "startedAt": started,
            "distinctFreshHeartbeats": len(fresh_seen),
            "last": observations[-1],
            "disconnectedAcceptance": False,
        }
        operation.save("recovery-summary.json", summary)
        operation.report("recovery-observed", summary)
    finally:
        released = json.loads(
            operation.execute(
                [
                    *lock_args,
                    "release",
                    operation.SERIAL,
                    "--fencing",
                    str(lock["fencing"]),
                    "--token-stdin",
                ],
                input_text=lock["owner_token"] + "\n",
            )
        )
        operation.save("recovery-lock-released.json", released)
        operation.report("lock-released", released)


if __name__ == "__main__":
    main()
