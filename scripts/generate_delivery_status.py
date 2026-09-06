#!/usr/bin/env python3
"""Create a delivery ledger from explicit, verifiable task evidence."""

from __future__ import annotations

import importlib.util
import json
import re
from datetime import date
from pathlib import Path
from types import ModuleType
from typing import Any

SOURCE = Path("docs/reference/tasks.json")
EVIDENCE_ROOT = Path("artifacts/tasks")
DESTINATION = Path("docs/delivery/task-status.json")
MARKDOWN = Path("docs/delivery/task-status.md")
HARDWARE_VALIDATOR = Path("scripts/validate-hardware-evidence.py")
ROLLOUT_VALIDATOR = Path("scripts/validate-rollout-evidence.py")
ROLLOUT_HARDWARE_TASKS = {"P5-003", "P5-006", "P5-007"}

SOFTWARE_STATUSES = {"unverified", "implemented"}
ACCEPTANCE_STATUSES = {"pending", "done", "blocked_hardware"}
PLACEHOLDER_EVIDENCE_PARTS = {
    "dryrun",
    "localonly",
    "offline",
    "example",
    "examples",
    "mock",
    "mocks",
    "sample",
    "samples",
    "simulation",
    "simulations",
    "simulator",
    "simulators",
    "synthetic",
    "template",
    "templates",
}


def _load_status(task_id: str, evidence_root: Path) -> dict[str, Any] | None:
    status_path = evidence_root / task_id / "status.json"
    if not status_path.is_file():
        return None
    status = json.loads(status_path.read_text(encoding="utf-8"))
    if not isinstance(status, dict):
        raise ValueError(f"{status_path} must contain a JSON object")
    return status


def _validated_evidence(
    task_id: str,
    status: dict[str, Any],
    repository_root: Path,
) -> list[str]:
    evidence = status.get("evidence", [])
    if not isinstance(evidence, list) or not all(isinstance(item, str) for item in evidence):
        raise ValueError(f"{task_id}: evidence must be a list of repository-relative paths")

    normalized: list[str] = []
    for raw_path in evidence:
        path = Path(raw_path)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError(
                f"{task_id}: evidence path must stay inside the repository: {raw_path}"
            )
        if not (repository_root / path).is_file():
            raise ValueError(f"{task_id}: evidence file does not exist: {raw_path}")
        normalized.append(path.as_posix())
    return normalized


def _reject_placeholder_completion(task_id: str, evidence: list[str]) -> None:
    for raw_path in evidence:
        path = Path(raw_path)
        parts: set[str] = set()
        for part in path.parts:
            tokens = re.findall(r"[a-z0-9]+", part.casefold())
            parts.update(tokens)
            parts.add("".join(tokens))
        dry_run = re.search(r"dry(?:[^a-z0-9]+)?run", raw_path, re.I) is not None
        if dry_run or parts & PLACEHOLDER_EVIDENCE_PARTS:
            raise ValueError(
                f"{task_id}: dry-run, mock, simulator, sample, or template files cannot "
                f"prove completion: {raw_path}"
            )


def _validator_path(task_id: str) -> Path:
    if task_id in ROLLOUT_HARDWARE_TASKS:
        return ROLLOUT_VALIDATOR
    return HARDWARE_VALIDATOR


def _load_hardware_validator(repository_root: Path, task_id: str) -> ModuleType:
    relative_validator = _validator_path(task_id)
    validator_path = repository_root / relative_validator
    if not validator_path.is_file():
        raise ValueError(f"hardware evidence validator does not exist: {relative_validator}")
    spec = importlib.util.spec_from_file_location(
        f"hardware_evidence_validator_{task_id.replace('-', '_')}", validator_path
    )
    if spec is None or spec.loader is None:
        raise ValueError(f"hardware evidence validator cannot be loaded: {relative_validator}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _validate_hardware_acceptance(
    task_id: str,
    status: dict[str, Any],
    evidence: list[str],
    evidence_root: Path,
    repository_root: Path,
) -> None:
    raw_bundle = status.get("hardwareEvidenceBundle")
    if not isinstance(raw_bundle, str) or not raw_bundle.strip():
        raise ValueError(f"{task_id}: hardware acceptance requires hardwareEvidenceBundle")
    bundle_path = Path(raw_bundle)
    if bundle_path.is_absolute() or ".." in bundle_path.parts:
        raise ValueError(f"{task_id}: hardwareEvidenceBundle must stay inside the repository")
    normalized_bundle = bundle_path.as_posix()
    if normalized_bundle not in evidence:
        raise ValueError(f"{task_id}: hardwareEvidenceBundle must be listed as task evidence")
    _reject_placeholder_completion(task_id, [normalized_bundle])

    expected_root = (evidence_root / task_id / "device-evidence").resolve()
    resolved_bundle = (repository_root / bundle_path).resolve()
    if expected_root not in resolved_bundle.parents:
        raise ValueError(
            f"{task_id}: hardwareEvidenceBundle must be inside the task device-evidence directory"
        )

    validator = _load_hardware_validator(repository_root, task_id)
    try:
        validated = validator.validate_bundle(resolved_bundle, task_id)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError(f"{task_id}: hardware evidence bundle is invalid: {exc}") from exc

    for relative in validated["evidenceFiles"]:
        referenced = (bundle_path.parent / relative).as_posix()
        if referenced not in evidence:
            raise ValueError(
                f"{task_id}: hardware evidence file must be listed as task evidence: {referenced}"
            )


def build_ledger(
    source: dict[str, Any],
    evidence_root: Path,
    repository_root: Path,
    generated_at: str,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for task in source["tasks"]:
        task_id = str(task["id"])
        hardware_required = bool(task["hardware_required"])
        status = _load_status(task_id, evidence_root)

        if status is None:
            software_status = "unverified"
            acceptance_status = "pending"
            hardware_evidence = False
            evidence: list[str] = []
            note = "No explicit task status or evidence has been recorded."
        else:
            software_status = str(status.get("softwareStatus", "unverified"))
            acceptance_status = str(status.get("acceptanceStatus", "pending"))
            raw_hardware_evidence = status.get("hardwareEvidence", False)
            if not isinstance(raw_hardware_evidence, bool):
                raise ValueError(f"{task_id}: hardwareEvidence must be a boolean")
            hardware_evidence = raw_hardware_evidence
            evidence = _validated_evidence(task_id, status, repository_root)
            note = str(status.get("note", ""))

            if software_status not in SOFTWARE_STATUSES:
                raise ValueError(f"{task_id}: invalid softwareStatus {software_status!r}")
            if acceptance_status not in ACCEPTANCE_STATUSES:
                raise ValueError(f"{task_id}: invalid acceptanceStatus {acceptance_status!r}")
            if acceptance_status != "pending" and not evidence:
                raise ValueError(f"{task_id}: non-pending acceptance requires evidence files")
            if acceptance_status == "done" and software_status != "implemented":
                raise ValueError(f"{task_id}: done acceptance requires implemented software")
            if acceptance_status == "done":
                _reject_placeholder_completion(task_id, evidence)
            if hardware_required and acceptance_status == "done" and not hardware_evidence:
                raise ValueError(f"{task_id}: hardware acceptance requires hardwareEvidence=true")
            if hardware_evidence and acceptance_status != "done":
                raise ValueError(f"{task_id}: hardwareEvidence=true requires acceptanceStatus=done")
            if hardware_evidence and not hardware_required:
                raise ValueError(f"{task_id}: non-hardware task cannot claim hardwareEvidence=true")
            if hardware_required and acceptance_status == "done":
                _validate_hardware_acceptance(
                    task_id,
                    status,
                    evidence,
                    evidence_root,
                    repository_root,
                )
            if not hardware_required and acceptance_status == "blocked_hardware":
                raise ValueError(f"{task_id}: non-hardware task cannot be blocked_hardware")

        rows.append(
            {
                "id": task_id,
                "phase": task["phase"],
                "title": task["title"],
                "softwareStatus": software_status,
                "acceptanceStatus": acceptance_status,
                "hardwareRequired": hardware_required,
                "hardwareEvidence": hardware_evidence,
                "evidence": evidence,
                "note": note,
            }
        )

    return {
        "schemaVersion": "2.0",
        "project": source["project"],
        "generatedAt": generated_at,
        "source": SOURCE.as_posix(),
        "summary": {
            "total": len(rows),
            "softwareImplemented": sum(row["softwareStatus"] == "implemented" for row in rows),
            "softwareUnverified": sum(row["softwareStatus"] == "unverified" for row in rows),
            "done": sum(row["acceptanceStatus"] == "done" for row in rows),
            "pending": sum(row["acceptanceStatus"] == "pending" for row in rows),
            "blockedHardware": sum(row["acceptanceStatus"] == "blocked_hardware" for row in rows),
        },
        "policy": {
            "statusRequiresExplicitEvidence": True,
            "mockDoesNotSatisfyHardwareAcceptance": True,
            "productionQualificationRequiresAuthorizedEvidence": True,
            "hardwareAcceptanceRequiresValidatedBundle": True,
        },
        "tasks": rows,
    }


def render_markdown(ledger: dict[str, Any]) -> str:
    summary = ledger["summary"]
    lines = [
        "# Delivery task status",
        "",
        f"Generated: {ledger['generatedAt']}",
        "",
        f"- Total architecture tasks: {summary['total']}",
        f"- Software implementation explicitly evidenced: {summary['softwareImplemented']}",
        f"- Software implementation still unverified: {summary['softwareUnverified']}",
        f"- Acceptance done with evidence: {summary['done']}",
        f"- Acceptance pending evidence: {summary['pending']}",
        f"- Awaiting authorized hardware evidence: {summary['blockedHardware']}",
        "",
        "A source file or passing repository-wide test does not automatically complete every "
        "architecture task. Each non-pending row must reference explicit evidence files. Mock "
        "and simulator results never satisfy "
        "hardware-required acceptance.",
        "",
        "| ID | Phase | Task | Software | Acceptance | Evidence |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in ledger["tasks"]:
        evidence = "<br>".join(f"`{item}`" for item in row["evidence"]) or "-"
        lines.append(
            f"| {row['id']} | {row['phase']} | {row['title']} | {row['softwareStatus']} | "
            f"{row['acceptanceStatus']} | {evidence} |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    repository_root = Path.cwd().resolve()
    source: dict[str, Any] = json.loads(SOURCE.read_text(encoding="utf-8"))
    ledger = build_ledger(source, EVIDENCE_ROOT, repository_root, date.today().isoformat())

    DESTINATION.parent.mkdir(parents=True, exist_ok=True)
    DESTINATION.write_text(
        json.dumps(ledger, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    MARKDOWN.write_text(render_markdown(ledger), encoding="utf-8")


if __name__ == "__main__":
    main()
