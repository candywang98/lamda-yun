#!/usr/bin/env python3
"""Validate authorized physical-device evidence without treating mocks as acceptance."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
PLACEHOLDER_PATTERN = re.compile(r"^(?:required|todo|tbd|pending)(?:[_ .-].*)?$", re.I)
PRIVATE_KEY_PATTERN = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----", re.I)
SECRET_ASSIGNMENT_PATTERN = re.compile(
    r"(?:password|api[_-]?key|access[_-]?token|client[_-]?secret)\s*[:=]\s*"
    r"(?P<value>\"[^\"]*\"|'[^']*'|\S+)",
    re.I,
)
BEARER_PATTERN = re.compile(r"authorization\s*:\s*bearer\s+\S+", re.I)
NON_HARDWARE_PATH_MARKERS = {
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
TASK_CHECKS = {
    "P2-011": {
        "inventory.read",
        "screenshot.capture",
        "ui.dump",
        "no_mutation",
    },
    "P3-012": {
        "account.authorization",
        "publish.prepare",
        "publish.commit",
        "publish.reconcile",
    },
    "P5-001": {
        "capacity.resources",
        "load.authorized_device",
        "soak.authorized_device",
        "telemetry.correlation",
    },
    "P5-002": {
        "chaos.disk_pressure",
        "chaos.edge_restart",
        "chaos.lease_loss",
        "chaos.network_outage",
        "recovery.verified",
    },
}


class EvidenceError(ValueError):
    pass


def _mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EvidenceError(f"{field} must be an object")
    return value


def _list(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise EvidenceError(f"{field} must be an array")
    return value


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvidenceError(f"{field} must be a non-empty string")
    return value


def _attested_text(value: Any, field: str) -> str:
    raw = _text(value, field).strip()
    if PLACEHOLDER_PATTERN.fullmatch(raw):
        raise EvidenceError(f"{field} cannot contain a template placeholder")
    return raw


def _path_markers(value: str) -> set[str]:
    tokens = re.findall(r"[a-z0-9]+", value.casefold())
    markers = set(tokens)
    for start in range(len(tokens)):
        for end in range(start + 2, min(len(tokens), start + 3) + 1):
            markers.add("".join(tokens[start:end]))
    return markers


def _reject_non_hardware_path(value: str, field: str) -> None:
    dry_run = re.search(r"dry(?:[^a-z0-9]+)?run", value, re.I) is not None
    if dry_run or _path_markers(value) & NON_HARDWARE_PATH_MARKERS:
        raise EvidenceError(f"{field} cannot identify dry-run, mock, or template evidence")


def _contains_secret_assignment(value: str) -> bool:
    public_values = {"", "0", "1", "false", "none", "null", "true"}
    for match in SECRET_ASSIGNMENT_PATTERN.finditer(value):
        assigned = match.group("value").strip("\"'").casefold()
        if assigned not in public_values:
            return True
    return False


def reject_secrets(value: Any, field: str = "bundle") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            reject_secrets(child, f"{field}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            reject_secrets(child, f"{field}[{index}]")
    elif isinstance(value, str) and (
        PRIVATE_KEY_PATTERN.search(value)
        or BEARER_PATTERN.search(value)
        or _contains_secret_assignment(value)
    ):
        raise EvidenceError(f"{field} contains secret or private-key material")


def _timestamp(value: Any, field: str) -> datetime:
    raw = _text(value, field)
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EvidenceError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise EvidenceError(f"{field} must include a timezone")
    return parsed


def _digest(value: Any, field: str) -> str:
    raw = _text(value, field).lower()
    if not SHA256_PATTERN.fullmatch(raw):
        raise EvidenceError(f"{field} must be a lowercase SHA256 digest")
    return raw


def _evidence_file(root: Path, raw_path: Any) -> Path:
    value = Path(_text(raw_path, "evidenceFiles.path"))
    _reject_non_hardware_path(value.as_posix(), "evidenceFiles.path")
    if value.is_absolute() or ".." in value.parts:
        raise EvidenceError("evidence file paths must stay inside device-evidence")
    resolved_root = root.resolve()
    resolved = (root / value).resolve()
    if resolved_root not in resolved.parents:
        raise EvidenceError("evidence file paths must stay inside device-evidence")
    if not resolved.is_file():
        raise EvidenceError(f"evidence file does not exist: {value.as_posix()}")
    return resolved


def validate_bundle(bundle_path: Path, expected_task_id: str | None = None) -> dict[str, Any]:
    _reject_non_hardware_path(bundle_path.name, "bundle path")
    bundle = _mapping(json.loads(bundle_path.read_text(encoding="utf-8")), "bundle")
    reject_secrets(bundle)
    task_id = _text(bundle.get("taskId"), "taskId")
    if task_id not in TASK_CHECKS:
        raise EvidenceError(f"unsupported hardware task: {task_id}")
    if expected_task_id is not None and task_id != expected_task_id:
        raise EvidenceError(f"bundle taskId {task_id} does not match {expected_task_id}")
    if bundle.get("schemaVersion") != "1.0":
        raise EvidenceError("schemaVersion must be 1.0")
    if bundle.get("evidenceKind") != "AUTHORIZED_PHYSICAL_DEVICE":
        raise EvidenceError("evidenceKind must be AUTHORIZED_PHYSICAL_DEVICE")
    if bundle.get("evidenceSource") != "AUTHORIZED_EXTERNAL_RUNNER":
        raise EvidenceError("evidenceSource must be AUTHORIZED_EXTERNAL_RUNNER")
    if bundle.get("hardwareEvidence") is not True:
        raise EvidenceError("hardwareEvidence must be true for acceptance")

    authorization = _mapping(bundle.get("authorization"), "authorization")
    _attested_text(authorization.get("ticket"), "authorization.ticket")
    _attested_text(authorization.get("approvedBy"), "authorization.approvedBy")
    approved_at = _timestamp(authorization.get("approvedAt"), "authorization.approvedAt")
    expires_at = _timestamp(authorization.get("expiresAt"), "authorization.expiresAt")
    if expires_at <= approved_at:
        raise EvidenceError("authorization must expire after approval")

    device = _mapping(bundle.get("device"), "device")
    if device.get("physical") is not True or device.get("emulator") is not False:
        raise EvidenceError("only a physical, non-emulator device is accepted")
    _digest(device.get("serialHash"), "device.serialHash")
    for field in ("model", "androidVersion", "lamdaVersion", "edgeId"):
        _attested_text(device.get(field), f"device.{field}")
    if task_id == "P2-011" and device["lamdaVersion"].strip().upper() == "UNAVAILABLE":
        raise EvidenceError("P2-011 requires a usable LAMDA version")

    apps = _list(bundle.get("targetApps"), "targetApps")
    if not apps:
        raise EvidenceError("targetApps cannot be empty")
    for index, raw_app in enumerate(apps):
        app = _mapping(raw_app, f"targetApps[{index}]")
        _attested_text(app.get("packageName"), f"targetApps[{index}].packageName")
        _attested_text(app.get("version"), f"targetApps[{index}].version")
        _digest(app.get("signatureDigest"), f"targetApps[{index}].signatureDigest")

    package = _mapping(bundle.get("automationPackage"), "automationPackage")
    _attested_text(package.get("name"), "automationPackage.name")
    _attested_text(package.get("version"), "automationPackage.version")
    _digest(package.get("artifactSha256"), "automationPackage.artifactSha256")

    execution = _mapping(bundle.get("execution"), "execution")
    if execution.get("mode") != "AUTHORIZED_HARDWARE":
        raise EvidenceError("execution.mode must be AUTHORIZED_HARDWARE")
    started_at = _timestamp(execution.get("startedAt"), "execution.startedAt")
    completed_at = _timestamp(execution.get("completedAt"), "execution.completedAt")
    if not (approved_at <= started_at <= completed_at <= expires_at):
        raise EvidenceError("execution must occur inside the authorization window")
    for field in ("correlationId", "workflowId"):
        _attested_text(execution.get(field), f"execution.{field}")
    if execution.get("outcome") != "PASSED":
        raise EvidenceError("execution outcome must be PASSED")
    if task_id == "P2-011" and execution.get("transport") != "LAMDA_DRIVER":
        raise EvidenceError("P2-011 execution.transport must be LAMDA_DRIVER")
    if task_id == "P3-012":
        _attested_text(execution.get("commitIntentId"), "execution.commitIntentId")
    if task_id == "P3-012":
        account = _mapping(bundle.get("accountAuthorization"), "accountAuthorization")
        if account.get("status") != "AUTHORIZED":
            raise EvidenceError("accountAuthorization.status must be AUTHORIZED")
        _text(account.get("platform"), "accountAuthorization.platform")
        _digest(account.get("accountRefHash"), "accountAuthorization.accountRefHash")
        checked_at = _timestamp(account.get("checkedAt"), "accountAuthorization.checkedAt")
        if not (approved_at <= checked_at <= started_at):
            raise EvidenceError("account authorization must be checked before execution")

    files: set[str] = set()
    for raw_file in _list(bundle.get("evidenceFiles"), "evidenceFiles"):
        file_entry = _mapping(raw_file, "evidenceFiles[]")
        relative = _text(file_entry.get("path"), "evidenceFiles.path")
        if relative in files:
            raise EvidenceError(f"duplicate evidence file: {relative}")
        path = _evidence_file(bundle_path.parent, relative)
        content = path.read_bytes()
        reject_secrets(content.decode("utf-8", errors="ignore"), f"evidenceFiles[{relative}]")
        actual = hashlib.sha256(content).hexdigest()
        expected = _digest(file_entry.get("sha256"), f"evidenceFiles[{relative}].sha256")
        if actual != expected:
            raise EvidenceError(f"evidence checksum mismatch: {relative}")
        files.add(relative)
    if not files:
        raise EvidenceError("evidenceFiles cannot be empty")

    checks = _list(bundle.get("checks"), "checks")
    passed_ids: set[str] = set()
    for raw_check in checks:
        check = _mapping(raw_check, "checks[]")
        check_id = _text(check.get("id"), "checks.id")
        if check.get("status") != "PASS":
            raise EvidenceError(f"check did not pass: {check_id}")
        references = _list(check.get("evidenceRefs"), f"checks[{check_id}].evidenceRefs")
        if not references or any(reference not in files for reference in references):
            raise EvidenceError(f"check has missing evidence references: {check_id}")
        passed_ids.add(check_id)
    missing = TASK_CHECKS[task_id] - passed_ids
    if missing:
        raise EvidenceError(f"required checks are missing: {sorted(missing)}")

    actions = _list(bundle.get("actions"), "actions")
    if task_id == "P2-011":
        required_actions = {"inventory.read", "screenshot.capture", "ui.dump"}
        observed_actions: set[str] = set()
        for raw_action in actions:
            action = _mapping(raw_action, "actions[]")
            if action.get("mode") != "READ_ONLY":
                raise EvidenceError("P2-011 accepts read-only actions only")
            observed_actions.add(_text(action.get("name"), "actions.name"))
        missing_actions = required_actions - observed_actions
        if missing_actions:
            raise EvidenceError(f"P2-011 actions are missing: {sorted(missing_actions)}")
    if task_id == "P3-012":
        required_modes = {"PREPARE", "COMMIT_SINGLE_SHOT", "RECONCILE"}
        observed_modes = {
            _text(_mapping(action, "actions[]").get("mode"), "actions.mode") for action in actions
        }
        missing_modes = required_modes - observed_modes
        if missing_modes:
            raise EvidenceError(f"P3-012 action modes are missing: {sorted(missing_modes)}")

    return {
        "taskId": task_id,
        "hardwareEvidence": True,
        "deviceSerialHash": device["serialHash"],
        "evidenceFiles": sorted(files),
        "evidenceFileCount": len(files),
        "passedChecks": sorted(passed_ids),
    }


def template(task_id: str) -> dict[str, Any]:
    if task_id not in TASK_CHECKS:
        raise EvidenceError(f"unsupported hardware task: {task_id}")
    value = {
        "schemaVersion": "1.0",
        "taskId": task_id,
        "evidenceKind": "TEMPLATE",
        "evidenceSource": "TEMPLATE",
        "hardwareEvidence": False,
        "authorization": {
            "ticket": "REQUIRED",
            "approvedBy": "REQUIRED",
            "approvedAt": None,
            "expiresAt": None,
        },
        "device": {
            "physical": True,
            "emulator": False,
            "serialHash": "REQUIRED_SHA256",
            "model": "REQUIRED",
            "androidVersion": "REQUIRED",
            "lamdaVersion": "REQUIRED",
            "edgeId": "REQUIRED",
        },
        "targetApps": [],
        "automationPackage": {
            "name": "REQUIRED",
            "version": "REQUIRED",
            "artifactSha256": "REQUIRED_SHA256",
        },
        "execution": {
            "mode": "PENDING_HARDWARE",
            "startedAt": None,
            "completedAt": None,
            "correlationId": "REQUIRED",
            "workflowId": "REQUIRED",
            "commitIntentId": "REQUIRED_WHEN_APPLICABLE",
            "outcome": "PENDING_HARDWARE",
        },
        "actions": [],
        "checks": [
            {"id": check_id, "status": "PENDING", "evidenceRefs": []}
            for check_id in sorted(TASK_CHECKS[task_id])
        ],
        "evidenceFiles": [],
    }
    if task_id == "P3-012":
        value["accountAuthorization"] = {
            "platform": "REQUIRED",
            "accountRefHash": "REQUIRED_SHA256",
            "status": "PENDING_HARDWARE",
            "checkedAt": None,
        }
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle", nargs="?", type=Path)
    parser.add_argument("--task-id", choices=sorted(TASK_CHECKS))
    parser.add_argument("--write-template", type=Path)
    args = parser.parse_args()
    if args.write_template is not None:
        if args.task_id is None:
            parser.error("--task-id is required with --write-template")
        args.write_template.parent.mkdir(parents=True, exist_ok=True)
        args.write_template.write_text(
            json.dumps(template(args.task_id), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return
    if args.bundle is None:
        parser.error("bundle is required")
    print(json.dumps(validate_bundle(args.bundle, args.task_id), indent=2))


if __name__ == "__main__":
    main()
