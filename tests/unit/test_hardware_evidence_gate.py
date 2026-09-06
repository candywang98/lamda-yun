from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest


def gate_module() -> ModuleType:
    path = Path("scripts/validate-hardware-evidence.py")
    spec = importlib.util.spec_from_file_location("hardware_evidence_gate", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def accepted_bundle(root: Path, task_id: str = "P2-011") -> Path:
    evidence = root / "device.log"
    evidence.write_text("authorized physical device evidence\n", encoding="utf-8")
    digest = hashlib.sha256(evidence.read_bytes()).hexdigest()
    required_checks = gate_module().TASK_CHECKS[task_id]
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
            "startedAt": "2026-08-31T03:30:00+00:00",
            "completedAt": "2026-08-31T04:00:00+00:00",
            "correlationId": "corr-1",
            "workflowId": "workflow-1",
            "commitIntentId": "intent-1",
            "outcome": "PASSED",
            "transport": "LAMDA_DRIVER",
        },
        "actions": [
            {"name": "inventory.read", "mode": "READ_ONLY"},
            {"name": "screenshot.capture", "mode": "READ_ONLY"},
            {"name": "ui.dump", "mode": "READ_ONLY"},
        ],
        "checks": [
            {"id": check_id, "status": "PASS", "evidenceRefs": ["device.log"]}
            for check_id in sorted(required_checks)
        ],
        "evidenceFiles": [{"path": "device.log", "sha256": digest}],
    }
    path = root / "bundle.json"
    path.write_text(json.dumps(bundle), encoding="utf-8")
    return path


def test_authorized_physical_device_bundle_passes(tmp_path: Path) -> None:
    result = gate_module().validate_bundle(accepted_bundle(tmp_path), "P2-011")
    assert result["hardwareEvidence"] is True
    assert result["evidenceFileCount"] == 1


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("hardwareEvidence", False, "hardwareEvidence must be true"),
        ("evidenceKind", "MOCK", "evidenceKind must be AUTHORIZED_PHYSICAL_DEVICE"),
        ("evidenceSource", "MOCK_RUNNER", "must be AUTHORIZED_EXTERNAL_RUNNER"),
        ("device.emulator", True, "physical, non-emulator"),
        ("execution.mode", "DRY_RUN", "execution.mode must be AUTHORIZED_HARDWARE"),
        ("execution.outcome", "MOCK_ONLY", "outcome must be PASSED"),
        ("execution.transport", "ADB_READ_ONLY_DIAGNOSTIC", "must be LAMDA_DRIVER"),
        ("device.lamdaVersion", "UNAVAILABLE", "requires a usable LAMDA version"),
    ],
)
def test_mock_or_non_hardware_bundle_is_rejected(
    tmp_path: Path, field: str, value: object, message: str
) -> None:
    path = accepted_bundle(tmp_path)
    bundle = json.loads(path.read_text(encoding="utf-8"))
    owner, _, name = field.partition(".")
    if name:
        bundle[owner][name] = value
    else:
        bundle[owner] = value
    path.write_text(json.dumps(bundle), encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        gate_module().validate_bundle(path)


def test_checksum_and_required_check_are_enforced(tmp_path: Path) -> None:
    path = accepted_bundle(tmp_path)
    bundle = json.loads(path.read_text(encoding="utf-8"))
    bundle["evidenceFiles"][0]["sha256"] = "d" * 64
    path.write_text(json.dumps(bundle), encoding="utf-8")
    with pytest.raises(ValueError, match="checksum mismatch"):
        gate_module().validate_bundle(path)

    path = accepted_bundle(tmp_path)
    bundle = json.loads(path.read_text(encoding="utf-8"))
    bundle["checks"].pop()
    path.write_text(json.dumps(bundle), encoding="utf-8")
    with pytest.raises(ValueError, match="required checks are missing"):
        gate_module().validate_bundle(path)


def test_template_is_explicitly_blocked_until_real_evidence_exists() -> None:
    value = gate_module().template("P3-012")
    assert value["evidenceKind"] == "TEMPLATE"
    assert value["evidenceSource"] == "TEMPLATE"
    assert value["hardwareEvidence"] is False
    assert value["execution"]["mode"] == "PENDING_HARDWARE"
    assert value["execution"]["outcome"] == "PENDING_HARDWARE"


@pytest.mark.parametrize(
    "task_id",
    ["P2-011", "P3-012"],
)
def test_remaining_hardware_templates_are_fail_closed(tmp_path: Path, task_id: str) -> None:
    module = gate_module()
    value = module.template(task_id)
    path = tmp_path / f"{task_id}-template.json"
    path.write_text(json.dumps(value), encoding="utf-8")

    assert value["hardwareEvidence"] is False
    assert value["execution"]["mode"] == "PENDING_HARDWARE"
    assert {check["id"] for check in value["checks"]} == module.TASK_CHECKS[task_id]
    with pytest.raises(ValueError, match="dry-run, mock, or template evidence"):
        module.validate_bundle(path, task_id)


@pytest.mark.parametrize(
    "task_id",
    ["P2-011", "P3-012"],
)
def test_checked_in_remaining_hardware_template_matches_generator(task_id: str) -> None:
    module = gate_module()
    path = Path("artifacts/tasks") / task_id / "device-evidence" / "template.json"

    assert json.loads(path.read_text(encoding="utf-8")) == module.template(task_id)


@pytest.mark.parametrize(
    "name",
    [
        "mock-device.log",
        "dry-run.json",
        "template.txt",
        "synthetic-result.log",
        "offline-result.log",
        "local-only-result.log",
    ],
)
def test_non_hardware_evidence_paths_are_rejected(tmp_path: Path, name: str) -> None:
    path = accepted_bundle(tmp_path)
    bundle = json.loads(path.read_text(encoding="utf-8"))
    original = tmp_path / "device.log"
    replacement = tmp_path / name
    original.rename(replacement)
    bundle["evidenceFiles"][0]["path"] = name
    bundle["checks"] = [{**check, "evidenceRefs": [name]} for check in bundle["checks"]]
    path.write_text(json.dumps(bundle), encoding="utf-8")

    with pytest.raises(ValueError, match="dry-run, mock, or template evidence"):
        gate_module().validate_bundle(path)


def test_template_placeholders_cannot_be_attested(tmp_path: Path) -> None:
    path = accepted_bundle(tmp_path)
    bundle = json.loads(path.read_text(encoding="utf-8"))
    bundle["authorization"]["ticket"] = "REQUIRED"
    path.write_text(json.dumps(bundle), encoding="utf-8")

    with pytest.raises(ValueError, match="template placeholder"):
        gate_module().validate_bundle(path)


def test_raw_device_serial_is_rejected_instead_of_being_stored(tmp_path: Path) -> None:
    path = accepted_bundle(tmp_path)
    bundle = json.loads(path.read_text(encoding="utf-8"))
    bundle["device"]["serialHash"] = "R58M123456Y"
    path.write_text(json.dumps(bundle), encoding="utf-8")

    with pytest.raises(ValueError, match="lowercase SHA256 digest"):
        gate_module().validate_bundle(path)


def test_secret_material_is_rejected_in_bundle_and_evidence(tmp_path: Path) -> None:
    path = accepted_bundle(tmp_path)
    bundle = json.loads(path.read_text(encoding="utf-8"))
    bundle["authorization"]["ticket"] = "access_token=not-for-delivery"
    path.write_text(json.dumps(bundle), encoding="utf-8")

    with pytest.raises(ValueError, match="secret or private-key material"):
        gate_module().validate_bundle(path)


def test_android_ui_password_boolean_is_not_treated_as_a_secret(tmp_path: Path) -> None:
    path = accepted_bundle(tmp_path)
    evidence = tmp_path / "device.log"
    evidence.write_text('<node password="false" text="" />\n', encoding="utf-8")
    bundle = json.loads(path.read_text(encoding="utf-8"))
    bundle["evidenceFiles"][0]["sha256"] = hashlib.sha256(evidence.read_bytes()).hexdigest()
    path.write_text(json.dumps(bundle), encoding="utf-8")

    result = gate_module().validate_bundle(path)

    assert result["hardwareEvidence"] is True

    path = accepted_bundle(tmp_path)
    evidence = tmp_path / "device.log"
    evidence.write_text(
        "-----BEGIN " + "PRIVATE KEY-----\nnot-for-delivery\n",
        encoding="utf-8",
    )
    bundle = json.loads(path.read_text(encoding="utf-8"))
    bundle["evidenceFiles"][0]["sha256"] = hashlib.sha256(evidence.read_bytes()).hexdigest()
    path.write_text(json.dumps(bundle), encoding="utf-8")

    with pytest.raises(ValueError, match="secret or private-key material"):
        gate_module().validate_bundle(path)


@pytest.mark.parametrize(
    ("task_id", "required"),
    [
        (
            "P5-001",
            {
                "capacity.resources",
                "load.authorized_device",
                "soak.authorized_device",
                "telemetry.correlation",
            },
        ),
        (
            "P5-002",
            {
                "chaos.disk_pressure",
                "chaos.edge_restart",
                "chaos.lease_loss",
                "chaos.network_outage",
                "recovery.verified",
            },
        ),
    ],
)
def test_load_and_chaos_templates_require_real_hardware_checks(
    tmp_path: Path, task_id: str, required: set[str]
) -> None:
    module = gate_module()
    value = module.template(task_id)

    assert value["hardwareEvidence"] is False
    assert {check["id"] for check in value["checks"]} == required
    with pytest.raises(ValueError, match="template evidence"):
        path = tmp_path / "template.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        module.validate_bundle(path, task_id)
