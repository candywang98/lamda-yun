from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest


def load_generator() -> ModuleType:
    path = Path(__file__).parents[2] / "scripts" / "generate_delivery_status.py"
    spec = importlib.util.spec_from_file_location("generate_delivery_status", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def source_task(*, hardware_required: bool = False, task_id: str = "P0-001") -> dict[str, object]:
    return {
        "project": "test",
        "tasks": [
            {
                "id": task_id,
                "phase": "phase",
                "title": "task",
                "hardware_required": hardware_required,
            }
        ],
    }


def write_status(root: Path, status: dict[str, object], task_id: str = "P0-001") -> None:
    task_dir = root / "artifacts" / "tasks" / task_id
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "summary.md").write_text("evidence\n", encoding="utf-8")
    (task_dir / "status.json").write_text(json.dumps(status), encoding="utf-8")


def write_hardware_bundle(root: Path, task_id: str = "P2-011") -> tuple[str, str]:
    validator_source = Path(__file__).parents[2] / "scripts" / "validate-hardware-evidence.py"
    validator = root / "scripts" / "validate-hardware-evidence.py"
    validator.parent.mkdir(parents=True)
    validator.write_text(validator_source.read_text(encoding="utf-8"), encoding="utf-8")

    evidence_dir = root / "artifacts" / "tasks" / task_id / "device-evidence"
    evidence_dir.mkdir(parents=True)
    capture = evidence_dir / "device.log"
    capture.write_text("authorized physical device evidence\n", encoding="utf-8")
    digest = hashlib.sha256(capture.read_bytes()).hexdigest()
    module_path = validator_source
    spec = importlib.util.spec_from_file_location("hardware_evidence_test_data", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    bundle = {
        "schemaVersion": "1.0",
        "taskId": task_id,
        "evidenceKind": "AUTHORIZED_PHYSICAL_DEVICE",
        "evidenceSource": "AUTHORIZED_EXTERNAL_RUNNER",
        "hardwareEvidence": True,
        "authorization": {
            "ticket": "SEC-2026-0831",
            "approvedBy": "security@example.test",
            "approvedAt": "2026-08-31T03:00:00+00:00",
            "expiresAt": "2026-08-31T05:00:00+00:00",
        },
        "device": {
            "physical": True,
            "emulator": False,
            "serialHash": "a" * 64,
            "model": "authorized-lab-device",
            "androidVersion": "14",
            "lamdaVersion": "10.8",
            "edgeId": "edge-lab-1",
        },
        "targetApps": [
            {
                "packageName": "com.example.target",
                "version": "8.32.1",
                "signatureDigest": "b" * 64,
            }
        ],
        "automationPackage": {
            "name": "publisher",
            "version": "1.0.0",
            "artifactSha256": "c" * 64,
        },
        "execution": {
            "mode": "AUTHORIZED_HARDWARE",
            "transport": "LAMDA_DRIVER",
            "startedAt": "2026-08-31T03:30:00+00:00",
            "completedAt": "2026-08-31T04:00:00+00:00",
            "correlationId": "corr-1",
            "workflowId": "workflow-1",
            "commitIntentId": "intent-1",
            "outcome": "PASSED",
        },
        "actions": [
            {"name": action, "mode": "READ_ONLY"}
            for action in ("inventory.read", "screenshot.capture", "ui.dump")
        ],
        "checks": [
            {"id": check_id, "status": "PASS", "evidenceRefs": ["device.log"]}
            for check_id in sorted(module.TASK_CHECKS.get(task_id, set()))
        ],
        "evidenceFiles": [{"path": "device.log", "sha256": digest}],
    }
    bundle_path = evidence_dir / "acceptance.json"
    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
    return (
        bundle_path.relative_to(root).as_posix(),
        capture.relative_to(root).as_posix(),
    )


def test_missing_status_is_unverified_and_pending(tmp_path: Path) -> None:
    module = load_generator()
    ledger = module.build_ledger(
        source_task(), tmp_path / "artifacts" / "tasks", tmp_path, "2026-08-31"
    )

    assert ledger["summary"] == {
        "total": 1,
        "softwareImplemented": 0,
        "softwareUnverified": 1,
        "done": 0,
        "pending": 1,
        "blockedHardware": 0,
    }
    assert ledger["tasks"][0]["acceptanceStatus"] == "pending"


def test_explicit_evidence_allows_non_hardware_completion(tmp_path: Path) -> None:
    module = load_generator()
    write_status(
        tmp_path,
        {
            "softwareStatus": "implemented",
            "acceptanceStatus": "done",
            "hardwareEvidence": False,
            "evidence": ["artifacts/tasks/P0-001/summary.md"],
        },
    )

    ledger = module.build_ledger(
        source_task(), tmp_path / "artifacts" / "tasks", tmp_path, "2026-08-31"
    )

    assert ledger["summary"]["softwareImplemented"] == 1
    assert ledger["summary"]["done"] == 1


def test_hardware_completion_without_hardware_evidence_is_rejected(tmp_path: Path) -> None:
    module = load_generator()
    write_status(
        tmp_path,
        {
            "softwareStatus": "implemented",
            "acceptanceStatus": "done",
            "hardwareEvidence": False,
            "evidence": ["artifacts/tasks/P0-001/summary.md"],
        },
    )

    with pytest.raises(ValueError, match="hardwareEvidence=true"):
        module.build_ledger(
            source_task(hardware_required=True),
            tmp_path / "artifacts" / "tasks",
            tmp_path,
            "2026-08-31",
        )


def test_missing_evidence_file_is_rejected(tmp_path: Path) -> None:
    module = load_generator()
    status_dir = tmp_path / "artifacts" / "tasks" / "P0-001"
    status_dir.mkdir(parents=True)
    (status_dir / "status.json").write_text(
        json.dumps(
            {
                "softwareStatus": "implemented",
                "acceptanceStatus": "done",
                "evidence": ["artifacts/tasks/P0-001/missing.md"],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="evidence file does not exist"):
        module.build_ledger(source_task(), tmp_path / "artifacts" / "tasks", tmp_path, "2026-08-31")


@pytest.mark.parametrize(
    "name",
    [
        "acceptance.example.json",
        "device-evidence-template.json",
        "sample/result.json",
        "mock/result.json",
        "dry-run/result.json",
        "acceptance-dry-run.json",
        "simulator/result.json",
        "synthetic/result.json",
        "offline/result.json",
        "local-only/result.json",
    ],
)
def test_placeholder_evidence_cannot_complete_a_task(tmp_path: Path, name: str) -> None:
    module = load_generator()
    task_dir = tmp_path / "artifacts" / "tasks" / "P0-001"
    evidence = task_dir / name
    evidence.parent.mkdir(parents=True)
    evidence.write_text("placeholder\n", encoding="utf-8")
    (task_dir / "status.json").write_text(
        json.dumps(
            {
                "softwareStatus": "implemented",
                "acceptanceStatus": "done",
                "hardwareEvidence": False,
                "evidence": [evidence.relative_to(tmp_path).as_posix()],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="cannot prove completion"):
        module.build_ledger(source_task(), tmp_path / "artifacts" / "tasks", tmp_path, "2026-08-31")


def test_hardware_evidence_flag_requires_done_acceptance(tmp_path: Path) -> None:
    module = load_generator()
    write_status(
        tmp_path,
        {
            "softwareStatus": "implemented",
            "acceptanceStatus": "blocked_hardware",
            "hardwareEvidence": True,
            "evidence": ["artifacts/tasks/P0-001/summary.md"],
        },
    )

    with pytest.raises(ValueError, match="requires acceptanceStatus=done"):
        module.build_ledger(
            source_task(hardware_required=True),
            tmp_path / "artifacts" / "tasks",
            tmp_path,
            "2026-08-31",
        )


def test_hardware_evidence_flag_must_be_boolean(tmp_path: Path) -> None:
    module = load_generator()
    write_status(
        tmp_path,
        {
            "softwareStatus": "implemented",
            "acceptanceStatus": "blocked_hardware",
            "hardwareEvidence": "true",
            "evidence": ["artifacts/tasks/P0-001/summary.md"],
        },
    )

    with pytest.raises(ValueError, match="must be a boolean"):
        module.build_ledger(
            source_task(hardware_required=True),
            tmp_path / "artifacts" / "tasks",
            tmp_path,
            "2026-08-31",
        )


def test_hardware_completion_requires_a_validated_bundle(tmp_path: Path) -> None:
    module = load_generator()
    task_id = "P2-011"
    bundle, capture = write_hardware_bundle(tmp_path, task_id)
    write_status(
        tmp_path,
        {
            "softwareStatus": "implemented",
            "acceptanceStatus": "done",
            "hardwareEvidence": True,
            "hardwareEvidenceBundle": bundle,
            "evidence": [
                f"artifacts/tasks/{task_id}/summary.md",
                bundle,
                capture,
            ],
        },
        task_id,
    )

    ledger = module.build_ledger(
        source_task(hardware_required=True, task_id=task_id),
        tmp_path / "artifacts" / "tasks",
        tmp_path,
        "2026-08-31",
    )

    assert ledger["summary"]["done"] == 1
    assert ledger["tasks"][0]["hardwareEvidence"] is True
    assert ledger["policy"]["hardwareAcceptanceRequiresValidatedBundle"] is True


def test_hardware_bundle_files_must_be_listed_as_task_evidence(tmp_path: Path) -> None:
    module = load_generator()
    task_id = "P2-011"
    bundle, _ = write_hardware_bundle(tmp_path, task_id)
    write_status(
        tmp_path,
        {
            "softwareStatus": "implemented",
            "acceptanceStatus": "done",
            "hardwareEvidence": True,
            "hardwareEvidenceBundle": bundle,
            "evidence": [f"artifacts/tasks/{task_id}/summary.md", bundle],
        },
        task_id,
    )

    with pytest.raises(ValueError, match="must be listed as task evidence"):
        module.build_ledger(
            source_task(hardware_required=True, task_id=task_id),
            tmp_path / "artifacts" / "tasks",
            tmp_path,
            "2026-08-31",
        )


def test_p5_hardware_completion_cannot_bypass_rollout_validator(tmp_path: Path) -> None:
    module = load_generator()
    task_id = "P5-003"
    bundle, capture = write_hardware_bundle(tmp_path, task_id)
    rollout_source = Path(__file__).parents[2] / "scripts" / "validate-rollout-evidence.py"
    rollout_validator = tmp_path / "scripts" / "validate-rollout-evidence.py"
    rollout_validator.write_text(rollout_source.read_text(encoding="utf-8"), encoding="utf-8")
    write_status(
        tmp_path,
        {
            "softwareStatus": "implemented",
            "acceptanceStatus": "done",
            "hardwareEvidence": True,
            "hardwareEvidenceBundle": bundle,
            "evidence": [
                f"artifacts/tasks/{task_id}/summary.md",
                bundle,
                capture,
            ],
        },
        task_id,
    )

    assert module._validator_path(task_id) == Path("scripts/validate-rollout-evidence.py")
    with pytest.raises(ValueError, match="evidenceClass"):
        module.build_ledger(
            source_task(hardware_required=True, task_id=task_id),
            tmp_path / "artifacts" / "tasks",
            tmp_path,
            "2026-08-31",
        )
