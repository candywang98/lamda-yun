#!/usr/bin/env python3
"""Run the local CloudCtl security and authorization acceptance suite."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.next")
    try:
        temporary.write_text(
            json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def run_acceptance(report_path: Path) -> int:
    commands = [
        ["bash", "scripts/check-security-boundaries.sh"],
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "tests/security/test_control_api_auth.py",
            "tests/security/test_repository_boundaries.py",
            "tests/security/test_penetration_authorization.py",
            "tests/integration/test_backend_operations.py",
            "tests/integration/test_backend_debug_sessions.py",
        ],
    ]
    checks: list[dict[str, Any]] = []
    passed = True
    for command in commands:
        started = time.perf_counter()
        completed = subprocess.run(  # noqa: S603 - commands are fixed repository checks.
            command,
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=300,
        )
        output = (completed.stdout + completed.stderr).strip()
        status = "passed" if completed.returncode == 0 else "failed"
        passed = passed and completed.returncode == 0
        checks.append(
            {
                "command": command,
                "durationSeconds": round(time.perf_counter() - started, 6),
                "exitCode": completed.returncode,
                "output": output[-20_000:],
                "status": status,
            }
        )

    report = {
        "acceptanceStatus": "pending_external",
        "checks": checks,
        "evidenceClass": "local_security_automation",
        "generatedAt": datetime.now(UTC).isoformat(),
        "hardwareEvidence": False,
        "schemaVersion": 1,
        "softwareStatus": "passed" if passed else "failed",
        "taskId": "P4-006",
        "warning": (
            "Automated local security checks do not replace an independent penetration test, "
            "production identity-provider validation, or authorized device certificate testing."
        ),
    }
    _atomic_json(report_path, report)
    print(f"{'PASS' if passed else 'FAIL'} {report_path}")
    return 0 if passed else 1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--report",
        type=Path,
        default=ROOT / "artifacts" / "tasks" / "P4-006" / "test-results.json",
    )
    args = parser.parse_args()
    raise SystemExit(run_acceptance(args.report.resolve()))


if __name__ == "__main__":
    main()
