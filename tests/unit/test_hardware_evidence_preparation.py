from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest


def script_module(name: str) -> ModuleType:
    path = Path("scripts") / name
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def inputs(root: Path, task_id: str) -> tuple[Path, Path, Path]:
    evidence_root = root / "device-evidence"
    evidence_root.mkdir()
    evidence = evidence_root / "runner.log"
    evidence.write_text("authorized external runner evidence\n", encoding="utf-8")
    authorization: dict[str, Any] = {
        "schemaVersion": "1.0",
        "taskId": task_id,
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
            "model": "authorized-device",
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
    }
    if task_id == "P3-012":
        authorization["accountAuthorization"] = {
            "platform": "authorized-platform-adapter",
            "accountRefHash": "d" * 64,
            "status": "AUTHORIZED",
            "checkedAt": "2026-08-31T03:20:00+00:00",
        }
    gate = script_module("validate-hardware-evidence.py")
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
    result = {
        "schemaVersion": "1.0",
        "taskId": task_id,
        "source": "AUTHORIZED_EXTERNAL_RUNNER",
        "executionMode": "PHYSICAL_DEVICE",
        "deviceAttestation": {
            "physical": True,
            "emulator": False,
            "serialHash": "a" * 64,
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
        "actions": actions,
        "checks": [
            {"id": check_id, "status": "PASS", "evidenceRefs": ["runner.log"]}
            for check_id in sorted(gate.TASK_CHECKS[task_id])
        ],
        "evidenceFiles": ["runner.log"],
    }
    authorization_path = root / "authorization.json"
    result_path = root / "run-result.json"
    authorization_path.write_text(json.dumps(authorization), encoding="utf-8")
    result_path.write_text(json.dumps(result), encoding="utf-8")
    return authorization_path, result_path, evidence_root


@pytest.mark.parametrize("task_id", ["P2-011", "P3-012"])
def test_offline_assembler_writes_and_validates_real_runner_contract(
    tmp_path: Path, task_id: str
) -> None:
    module = script_module("prepare-hardware-evidence.py")
    authorization, result, evidence_root = inputs(tmp_path, task_id)
    bundle = module.assemble_bundle(
        task_id=task_id,
        authorization_path=authorization,
        run_result_path=result,
        evidence_root=evidence_root,
        hardware_attested=True,
    )
    output = evidence_root / "bundle.json"

    validation = module.write_and_validate_bundle(
        bundle=bundle,
        output=output,
        evidence_root=evidence_root,
        overwrite=False,
    )

    assert validation["taskId"] == task_id
    assert validation["hardwareEvidence"] is True
    assert output.is_file()
    stored = json.loads(output.read_text(encoding="utf-8"))
    assert stored["evidenceKind"] == "AUTHORIZED_PHYSICAL_DEVICE"
    assert stored["evidenceSource"] == "AUTHORIZED_EXTERNAL_RUNNER"
    assert stored["execution"]["mode"] == "AUTHORIZED_HARDWARE"


def test_default_cli_is_dry_run_template_and_writes_nothing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    module = script_module("prepare-hardware-evidence.py")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["prepare-hardware-evidence.py", "--task-id", "P3-012"])

    module.main()

    output = json.loads(capsys.readouterr().out)
    assert output["mode"] == "dry-run-template"
    assert output["hardwareEvidence"] is False
    assert output["runResult"]["executionMode"] == "DRY_RUN"
    assert list(tmp_path.iterdir()) == []


def test_preview_hashes_existing_evidence_but_never_claims_hardware(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    module = script_module("prepare-hardware-evidence.py")
    authorization, result, evidence_root = inputs(tmp_path, "P2-011")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "prepare-hardware-evidence.py",
            "--task-id",
            "P2-011",
            "--authorization",
            str(authorization),
            "--run-result",
            str(result),
            "--evidence-root",
            str(evidence_root),
        ],
    )

    module.main()

    output = json.loads(capsys.readouterr().out)
    assert output["mode"] == "dry-run-preview"
    assert output["hardwareEvidence"] is False
    assert output["bundle"]["hardwareEvidence"] is False
    assert output["bundle"]["evidenceKind"] == "DRY_RUN_PREVIEW"
    assert output["bundle"]["evidenceSource"] == "DRY_RUN_PREVIEW"
    assert output["bundle"]["execution"]["mode"] == "DRY_RUN"
    assert not (evidence_root / "bundle.json").exists()


@pytest.mark.parametrize("source", ["authorization", "run_result"])
def test_raw_or_invalid_serial_hash_is_rejected(tmp_path: Path, source: str) -> None:
    module = script_module("prepare-hardware-evidence.py")
    authorization_path, result_path, evidence_root = inputs(tmp_path, "P2-011")
    path = authorization_path if source == "authorization" else result_path
    value = json.loads(path.read_text(encoding="utf-8"))
    if source == "authorization":
        value["device"]["serialHash"] = "b0644fb5"
    else:
        value["deviceAttestation"]["serialHash"] = "not-64-hex"
    path.write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(ValueError, match="lowercase SHA256 digest"):
        module.assemble_bundle(
            task_id="P2-011",
            authorization_path=authorization_path,
            run_result_path=result_path,
            evidence_root=evidence_root,
            hardware_attested=False,
        )


@pytest.mark.parametrize("source", ["authorization", "run_result"])
def test_secret_material_is_rejected_before_preview(tmp_path: Path, source: str) -> None:
    module = script_module("prepare-hardware-evidence.py")
    authorization_path, result_path, evidence_root = inputs(tmp_path, "P2-011")
    path = authorization_path if source == "authorization" else result_path
    value = json.loads(path.read_text(encoding="utf-8"))
    value["unexpectedMaterial"] = "-----BEGIN " + "PRIVATE KEY-----"
    path.write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(ValueError, match="secret or private-key material"):
        module.assemble_bundle(
            task_id="P2-011",
            authorization_path=authorization_path,
            run_result_path=result_path,
            evidence_root=evidence_root,
            hardware_attested=False,
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("source", "MOCK_RUNNER", "AUTHORIZED_EXTERNAL_RUNNER"),
        ("executionMode", "SIMULATOR", "PHYSICAL_DEVICE"),
    ],
)
def test_mock_and_simulator_results_are_rejected(
    tmp_path: Path, field: str, value: str, message: str
) -> None:
    module = script_module("prepare-hardware-evidence.py")
    authorization, result_path, evidence_root = inputs(tmp_path, "P2-011")
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result[field] = value
    result_path.write_text(json.dumps(result), encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        module.assemble_bundle(
            task_id="P2-011",
            authorization_path=authorization,
            run_result_path=result_path,
            evidence_root=evidence_root,
            hardware_attested=True,
        )


def test_invalid_bundle_is_removed_after_final_gate_failure(tmp_path: Path) -> None:
    module = script_module("prepare-hardware-evidence.py")
    authorization, result_path, evidence_root = inputs(tmp_path, "P2-011")
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result["actions"][0]["mode"] = "MUTATING"
    result_path.write_text(json.dumps(result), encoding="utf-8")
    bundle = module.assemble_bundle(
        task_id="P2-011",
        authorization_path=authorization,
        run_result_path=result_path,
        evidence_root=evidence_root,
        hardware_attested=True,
    )
    output = evidence_root / "bundle.json"

    with pytest.raises(ValueError, match="read-only actions only"):
        module.write_and_validate_bundle(
            bundle=bundle,
            output=output,
            evidence_root=evidence_root,
            overwrite=False,
        )
    assert not output.exists()
