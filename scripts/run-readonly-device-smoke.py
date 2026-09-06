#!/usr/bin/env python3
"""Run the P2-011 allowlisted physical-device diagnostic without mutating the device."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cloudctl_lamda_driver import CommandExecutor, ReadOnlyAdbProbe


def _now() -> datetime:
    return datetime.now(UTC)


def plan(serial: str, target_package: str) -> dict[str, Any]:
    return {
        "mode": "dry-run",
        "taskId": "P2-011",
        "serialHash": hashlib.sha256(serial.encode("utf-8")).hexdigest(),
        "targetPackage": target_package,
        "operations": [
            "inventory.read",
            "screenshot.capture",
            "ui.dump",
            "lamda.package.detect",
            "lamda.port.detect",
        ],
        "mutatingOperations": [],
        "note": "No device command was executed. Use --execute-read-only explicitly.",
    }


def run_smoke(
    *,
    adb_path: Path,
    serial: str,
    target_package: str,
    output_dir: Path,
    executor: CommandExecutor | None = None,
) -> dict[str, Any]:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("output directory must be absent or empty")
    output_dir.mkdir(parents=True, exist_ok=True)
    started_at = _now()
    probe = (
        ReadOnlyAdbProbe(adb_path=adb_path, serial=serial)
        if executor is None
        else ReadOnlyAdbProbe(adb_path=adb_path, serial=serial, executor=executor)
    )
    inventory = probe.inventory(target_package)
    screenshot = probe.screenshot()
    ui_dump = probe.dump_ui()
    completed_at = _now()

    (output_dir / "inventory.json").write_text(
        json.dumps(inventory, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (output_dir / "screenshot.png").write_bytes(screenshot)
    (output_dir / "ui.xml").write_text(ui_dump, encoding="utf-8")
    audit = {
        "schemaVersion": "1.0",
        "transport": inventory["transport"],
        "operations": list(probe.operations),
        "mutatingOperationsExecuted": False,
        "rawCommandArgumentsRecorded": False,
    }
    (output_dir / "command-audit.json").write_text(
        json.dumps(audit, indent=2) + "\n", encoding="utf-8"
    )
    evidence_files = ["inventory.json", "screenshot.png", "ui.xml", "command-audit.json"]
    lamda_ready = (
        bool(inventory["lamdaPackages"])
        and bool(inventory["lamdaPortListening"])
        and inventory["lamdaVersion"] not in {"", "UNAVAILABLE"}
    )
    blockers = []
    if not inventory["lamdaPackages"]:
        blockers.append("No LAMDA package was detected on the authorized device")
    if not inventory["lamdaPortListening"]:
        blockers.append("LAMDA service port 65000 is not listening on the authorized device")
    if inventory["lamdaVersion"] in {"", "UNAVAILABLE"}:
        blockers.append("LAMDA SDK version is unavailable to the ADB diagnostic")

    result = {
        "schemaVersion": "1.0",
        "taskId": "P2-011",
        "source": "AUTHORIZED_EXTERNAL_RUNNER",
        "executionMode": "PHYSICAL_DEVICE",
        "diagnosticOnly": True,
        "hardwareEvidence": False,
        "acceptanceStatus": "blocked_hardware",
        "deviceAttestation": {
            "physical": True,
            "emulator": False,
            "serialHash": inventory["serialHash"],
            "model": inventory["model"],
        },
        "execution": {
            "mode": "READ_ONLY_DIAGNOSTIC",
            "startedAt": started_at.isoformat(),
            "completedAt": completed_at.isoformat(),
            "correlationId": f"p2-011-{started_at.strftime('%Y%m%dT%H%M%SZ')}",
            "workflowId": "p2-011-readonly-diagnostic",
            "commitIntentId": "NOT_APPLICABLE",
            "outcome": "PASSED",
            "transport": inventory["transport"],
        },
        "actions": [
            {"name": "inventory.read", "mode": "READ_ONLY"},
            {"name": "screenshot.capture", "mode": "READ_ONLY"},
            {"name": "ui.dump", "mode": "READ_ONLY"},
        ],
        "checks": [
            {"id": "inventory.read", "status": "PASS", "evidenceRefs": ["inventory.json"]},
            {
                "id": "screenshot.capture",
                "status": "PASS",
                "evidenceRefs": ["screenshot.png"],
            },
            {"id": "ui.dump", "status": "PASS", "evidenceRefs": ["ui.xml"]},
            {
                "id": "no_mutation",
                "status": "PASS",
                "evidenceRefs": ["command-audit.json"],
            },
        ],
        "evidenceFiles": evidence_files,
        "acceptanceReady": lamda_ready,
        "blockers": blockers,
    }
    (output_dir / "run-result.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="P2-011 read-only diagnostic; contains no input, install, or publish action."
    )
    parser.add_argument("--adb", type=Path, required=True)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--target-package", default="com.android.settings")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--execute-read-only", action="store_true")
    args = parser.parse_args()
    if not args.execute_read_only:
        print(json.dumps(plan(args.serial, args.target_package), indent=2))
        return
    if args.output is None:
        parser.error("--execute-read-only requires --output")
    print(
        json.dumps(
            run_smoke(
                adb_path=args.adb,
                serial=args.serial,
                target_package=args.target_package,
                output_dir=args.output,
            ),
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
