#!/usr/bin/env python3
"""Assemble offline hardware evidence from explicit authorization and runner output."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
from pathlib import Path
from types import ModuleType
from typing import Any, cast

SUPPORTED_TASKS = ("P2-011", "P3-012")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class PreparationError(ValueError):
    pass


def _load_gate() -> ModuleType:
    path = Path(__file__).with_name("validate-hardware-evidence.py")
    spec = importlib.util.spec_from_file_location("cloudctl_hardware_evidence_gate", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load hardware evidence gate")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PreparationError(f"{field} must be an object")
    return value


def _list(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise PreparationError(f"{field} must be an array")
    return value


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PreparationError(f"{field} must be a non-empty string")
    return value


def _digest(value: Any, field: str) -> str:
    raw = _text(value, field).lower()
    if not SHA256_PATTERN.fullmatch(raw):
        raise PreparationError(f"{field} must be a lowercase SHA256 digest")
    return raw


def contract_template(task_id: str) -> dict[str, Any]:
    if task_id not in SUPPORTED_TASKS:
        raise PreparationError(f"unsupported task: {task_id}")
    authorization: dict[str, Any] = {
        "schemaVersion": "1.0",
        "taskId": task_id,
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
    }
    if task_id == "P3-012":
        authorization["accountAuthorization"] = {
            "platform": "REQUIRED",
            "accountRefHash": "REQUIRED_SHA256",
            "status": "PENDING_HARDWARE",
            "checkedAt": None,
        }
    actions = (
        [
            {"name": "inventory.read", "mode": "READ_ONLY"},
            {"name": "screenshot.capture", "mode": "READ_ONLY"},
            {"name": "ui.dump", "mode": "READ_ONLY"},
        ]
        if task_id == "P2-011"
        else [
            {"name": "publish.prepare", "mode": "PREPARE"},
            {"name": "publish.commit", "mode": "COMMIT_SINGLE_SHOT"},
            {"name": "publish.reconcile", "mode": "RECONCILE"},
        ]
    )
    run_result = {
        "schemaVersion": "1.0",
        "taskId": task_id,
        "source": "DRY_RUN_TEMPLATE",
        "executionMode": "DRY_RUN",
        "deviceAttestation": {"physical": False, "emulator": False},
        "execution": {
            "mode": "PENDING_HARDWARE",
            "startedAt": None,
            "completedAt": None,
            "correlationId": "REQUIRED",
            "workflowId": "REQUIRED",
            "commitIntentId": "REQUIRED_FOR_P3_012",
            "outcome": "PENDING_HARDWARE",
        },
        "actions": actions,
        "checks": [
            {"id": check_id, "status": "PENDING", "evidenceRefs": []}
            for check_id in sorted(_load_gate().TASK_CHECKS[task_id])
        ],
        "evidenceFiles": [],
    }
    return {
        "mode": "dry-run-template",
        "hardwareEvidence": False,
        "authorizationConfig": authorization,
        "runResult": run_result,
    }


def _load_input(path: Path, name: str) -> dict[str, Any]:
    try:
        return _mapping(json.loads(path.read_text(encoding="utf-8")), name)
    except (OSError, json.JSONDecodeError) as exc:
        raise PreparationError(f"unable to read {name}: {path}") from exc


def _safe_evidence_path(root: Path, raw_path: Any) -> tuple[str, Path]:
    relative = Path(_text(raw_path, "evidenceFiles[]"))
    if relative.is_absolute() or ".." in relative.parts:
        raise PreparationError("evidence paths must stay inside evidenceRoot")
    resolved_root = root.resolve()
    resolved = (root / relative).resolve()
    if resolved_root not in resolved.parents or not resolved.is_file():
        raise PreparationError(f"evidence file does not exist inside evidenceRoot: {relative}")
    return relative.as_posix(), resolved


def assemble_bundle(
    *,
    task_id: str,
    authorization_path: Path,
    run_result_path: Path,
    evidence_root: Path,
    hardware_attested: bool,
) -> dict[str, Any]:
    if task_id not in SUPPORTED_TASKS:
        raise PreparationError(f"unsupported task: {task_id}")
    authorization = _load_input(authorization_path, "authorizationConfig")
    result = _load_input(run_result_path, "runResult")
    gate = _load_gate()
    gate.reject_secrets(authorization, "authorizationConfig")
    gate.reject_secrets(result, "runResult")
    for name, value in (("authorizationConfig", authorization), ("runResult", result)):
        if value.get("schemaVersion") != "1.0":
            raise PreparationError(f"{name}.schemaVersion must be 1.0")
        if value.get("taskId") != task_id:
            raise PreparationError(f"{name}.taskId must match {task_id}")

    if result.get("source") != "AUTHORIZED_EXTERNAL_RUNNER":
        raise PreparationError("runResult.source must be AUTHORIZED_EXTERNAL_RUNNER")
    if result.get("executionMode") != "PHYSICAL_DEVICE":
        raise PreparationError("runResult.executionMode must be PHYSICAL_DEVICE")
    attestation = _mapping(result.get("deviceAttestation"), "deviceAttestation")
    if attestation.get("physical") is not True or attestation.get("emulator") is not False:
        raise PreparationError("runner must attest a physical, non-emulator device")
    device = _mapping(authorization.get("device"), "authorizationConfig.device")
    authorized_serial = _digest(device.get("serialHash"), "authorizationConfig.device.serialHash")
    runner_serial = _digest(attestation.get("serialHash"), "runResult.deviceAttestation.serialHash")
    if runner_serial != authorized_serial:
        raise PreparationError("runner device serialHash does not match authorization")

    evidence_files: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw_path in _list(result.get("evidenceFiles"), "runResult.evidenceFiles"):
        relative, path = _safe_evidence_path(evidence_root, raw_path)
        if relative in seen:
            raise PreparationError(f"duplicate evidence file: {relative}")
        seen.add(relative)
        evidence_files.append(
            {"path": relative, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        )
    if not evidence_files:
        raise PreparationError("runResult.evidenceFiles cannot be empty")

    execution = dict(_mapping(result.get("execution"), "execution"))
    execution["mode"] = "AUTHORIZED_HARDWARE" if hardware_attested else "DRY_RUN"
    bundle = {
        "schemaVersion": "1.0",
        "taskId": task_id,
        "evidenceKind": ("AUTHORIZED_PHYSICAL_DEVICE" if hardware_attested else "DRY_RUN_PREVIEW"),
        "evidenceSource": (
            "AUTHORIZED_EXTERNAL_RUNNER" if hardware_attested else "DRY_RUN_PREVIEW"
        ),
        "hardwareEvidence": hardware_attested is True,
        "authorization": _mapping(authorization.get("authorization"), "authorization"),
        "device": device,
        "targetApps": _list(authorization.get("targetApps"), "targetApps"),
        "automationPackage": _mapping(authorization.get("automationPackage"), "automationPackage"),
        "execution": execution,
        "actions": _list(result.get("actions"), "actions"),
        "checks": _list(result.get("checks"), "checks"),
        "evidenceFiles": evidence_files,
    }
    if task_id == "P3-012":
        bundle["accountAuthorization"] = _mapping(
            authorization.get("accountAuthorization"), "accountAuthorization"
        )
    return bundle


def write_and_validate_bundle(
    *, bundle: dict[str, Any], output: Path, evidence_root: Path, overwrite: bool
) -> dict[str, Any]:
    if output.parent.resolve() != evidence_root.resolve():
        raise PreparationError("output must be directly inside evidenceRoot")
    if output.exists() and not overwrite:
        raise PreparationError(f"output already exists: {output}")
    output.write_text(json.dumps(bundle, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    try:
        return cast(
            dict[str, Any],
            _load_gate().validate_bundle(output, str(bundle["taskId"])),
        )
    except Exception:
        output.unlink(missing_ok=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Offline-only evidence preparation; never connects to devices or platforms."
    )
    parser.add_argument("--task-id", choices=SUPPORTED_TASKS, default="P2-011")
    parser.add_argument("--authorization", type=Path)
    parser.add_argument("--run-result", type=Path)
    parser.add_argument("--evidence-root", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--attest-physical-device", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    inputs = (args.authorization, args.run_result, args.evidence_root)
    if not any(inputs):
        print(json.dumps(contract_template(args.task_id), indent=2, ensure_ascii=False))
        return
    if not all(inputs):
        parser.error("--authorization, --run-result, and --evidence-root are required together")

    bundle = assemble_bundle(
        task_id=args.task_id,
        authorization_path=args.authorization,
        run_result_path=args.run_result,
        evidence_root=args.evidence_root,
        hardware_attested=args.write and args.attest_physical_device,
    )
    if not args.write:
        print(
            json.dumps(
                {
                    "mode": "dry-run-preview",
                    "hardwareEvidence": False,
                    "note": "No file written and no hardware acceptance claimed.",
                    "bundle": bundle,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return
    if not args.attest_physical_device:
        parser.error("--write requires --attest-physical-device")
    if args.output is None:
        parser.error("--write requires --output")
    validation = write_and_validate_bundle(
        bundle=bundle,
        output=args.output,
        evidence_root=args.evidence_root,
        overwrite=args.overwrite,
    )
    print(json.dumps({"output": str(args.output), "validation": validation}, indent=2))


if __name__ == "__main__":
    main()
