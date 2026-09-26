#!/usr/bin/env python3
"""Explicit, read-only ADB cgroup-v2 probe; never changes power or app state."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import Any
from uuid import UUID


def process_start(stat: str, pid: str) -> str:
    head, separator, tail = stat.rpartition(")")
    fields = tail.split()
    if not separator or not head.startswith(f"{pid} (") or len(fields) < 20:
        raise ValueError("unreadable process identity")
    if not fields[19].isdigit():
        raise ValueError("invalid process start time")
    return fields[19]


def unified_path(cgroups: str) -> str:
    paths = [line[3:] for line in cgroups.splitlines() if line.startswith("0::")]
    if len(paths) != 1:
        raise ValueError("cgroup v2 membership unavailable")
    path = paths[0]
    if not re.fullmatch(r"/[A-Za-z0-9_./-]*", path) or any(
        part in {".", ".."} for part in path.split("/")
    ):
        raise ValueError("invalid cgroup path")
    if len(PurePosixPath(path).parts) > 16:
        raise ValueError("cgroup ancestry exceeds probe bound")
    return str(PurePosixPath(path))


def cgroup_paths(path: str) -> list[str]:
    current = PurePosixPath(path)
    paths = []
    while current != PurePosixPath("/"):
        paths.append(str(PurePosixPath("/sys/fs/cgroup") / current.relative_to("/")))
        current = current.parent
    return paths


def bit(text: str) -> int | None:
    return int(text.strip()) if text.strip() in {"0", "1"} else None


def event_bit(events: str, key: str = "frozen") -> int | None:
    values = [
        fields for line in events.splitlines() if (fields := line.split()) and fields[0] == key
    ]
    return bit(values[0][1]) if len(values) == 1 and len(values[0]) == 2 else None


def classify(rounds: list[list[dict[str, Any]]]) -> dict[str, Any]:
    """Two samples are evidence of observations, not an atomic or continuous interval."""
    result: dict[str, Any] = {
        "state": "UNKNOWN",
        "freezeObserved": any(row["frozen"] == 1 for rows in rounds for row in rows),
        "requestingPaths": [],
        "policyOwner": "UNKNOWN",
    }
    if len(rounds) != 2 or not rounds[0] or len(rounds[0]) != len(rounds[1]):
        return result
    if any(
        row["freeze"] is None or row["frozen"] is None or row["populated"] != 1
        for rows in rounds
        for row in rows
    ):
        return result
    if any(
        (a["path"], a["freeze"], a["frozen"]) != (b["path"], b["freeze"], b["frozen"])
        for a, b in zip(*rounds, strict=True)
    ):
        result["state"] = "TRANSITION_OBSERVED"
        return result
    result["requestingPaths"] = [row["path"] for row in rounds[1] if row["freeze"] == 1]
    if rounds[1][0]["frozen"] == 1:
        result["state"] = "FROZEN_OBSERVED"
    elif result["requestingPaths"] or result["freezeObserved"]:
        result["state"] = "TRANSITION_OBSERVED"
    else:
        result["state"] = "NOT_FROZEN_AT_SAMPLES"
    return result


class AdbReader:
    def __init__(self, adb: str, serial: str, timeout: float) -> None:
        self.adb, self.serial, self.timeout = adb, serial, timeout
        self.reads: list[dict[str, Any]] = []

    def read(self, *arguments: str) -> str:
        entry: dict[str, Any] = {
            "startedAt": datetime.now(UTC).isoformat(),
            "arguments": list(arguments),
        }
        try:
            # Call sites allow only pidof/cat with validated package, PID and cgroup paths.
            response = subprocess.run(  # noqa: S603
                [self.adb, "-s", self.serial, "shell", *arguments],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
            entry["exitCode"] = response.returncode
            text = response.stdout if response.returncode == 0 else ""
        except subprocess.TimeoutExpired:
            entry["error"] = "TIMEOUT"
            text = ""
        except OSError:
            entry["error"] = "ADB_UNAVAILABLE"
            text = ""
        entry["completedAt"] = datetime.now(UTC).isoformat()
        self.reads.append(entry)
        return text


def identity(reader: AdbReader, package: str) -> dict[str, str]:
    boot_id = reader.read("cat", "/proc/sys/kernel/random/boot_id").strip()
    try:
        UUID(boot_id)
    except ValueError as error:
        raise ValueError("unreadable boot identity") from error
    pid = reader.read("pidof", package).strip()
    if not re.fullmatch(r"[1-9][0-9]*", pid):
        raise ValueError("one live package PID required")
    return {
        "bootId": boot_id,
        "pid": pid,
        "startTicks": process_start(reader.read("cat", f"/proc/{pid}/stat"), pid),
        "cgroup": unified_path(reader.read("cat", f"/proc/{pid}/cgroup")),
    }


def cgroup_sample(reader: AdbReader, directory: str) -> dict[str, Any]:
    freeze = bit(reader.read("cat", f"{directory}/cgroup.freeze"))
    events = reader.read("cat", f"{directory}/cgroup.events")
    return {
        "path": directory,
        "freeze": freeze,
        "frozen": event_bit(events),
        "populated": event_bit(events, "populated"),
    }


def collect(reader: AdbReader, package: str) -> dict[str, Any]:
    if not re.fullmatch(r"[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+", package):
        raise ValueError("invalid package")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]*", reader.serial):
        raise ValueError("invalid exact device serial")
    result: dict[str, Any] = {
        "serial": reader.serial,
        "package": package,
        "startedAt": datetime.now(UTC).isoformat(),
        "state": "UNKNOWN",
        "diagnosticOnly": True,
        "businessAcceptance": False,
        "mutatingOperations": [],
        "atomicSnapshot": False,
        "identityMatchesAtChecks": None,
        "identityChecks": [],
        "rounds": [],
    }
    try:
        initial = identity(reader, package)
        result["process"] = initial
        result["identityChecks"].append(initial)
        for _ in range(2):
            result["rounds"].append(
                [cgroup_sample(reader, directory) for directory in cgroup_paths(initial["cgroup"])]
            )
            checked = identity(reader, package)
            result["identityChecks"].append(checked)
            if checked != initial:
                break
        result.update(classify(result["rounds"]))
        if any(checked != initial for checked in result["identityChecks"]):
            result["state"] = "PROCESS_CHANGED"
            result["requestingPaths"] = []
            result["identityMatchesAtChecks"] = False
        else:
            result["identityMatchesAtChecks"] = True
    except ValueError as error:
        result["state"] = "UNKNOWN"
        result["reason"] = str(error)
        result["requestingPaths"] = []
    result["completedAt"] = datetime.now(UTC).isoformat()
    result["reads"] = reader.reads
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--package", default="com.company.cloudctl.companion")
    parser.add_argument("--timeout", type=float, default=5)
    parser.add_argument("--execute-read-only", action="store_true")
    args = parser.parse_args()
    if not 0 < args.timeout <= 30:
        parser.error("--timeout must be greater than 0 and at most 30 seconds")
    if not args.execute_read_only:
        print(json.dumps({"mode": "dry-run", "operations": ["pidof", "cat"], "executed": False}))
        return
    adb = shutil.which("adb")
    if adb is None:
        parser.error("adb not found")
    try:
        report = collect(AdbReader(adb, args.serial, args.timeout), args.package)
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
