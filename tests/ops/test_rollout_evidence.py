from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "validate-rollout-evidence.py"
CONTRACT = (
    Path(__file__).resolve().parents[2] / "docs" / "contracts" / ("rollout-evidence-contracts.json")
)
SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
SHA_D = "d" * 64


def load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("rollout_evidence", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def environment(
    *,
    serial: str = SHA_A,
    android: str = "14",
    lamda: str = "10.8",
    app_version: str = "8.32.1",
) -> dict[str, Any]:
    return {
        "physical": True,
        "emulator": False,
        "serialHash": serial,
        "model": "authorized-lab-device",
        "androidVersion": android,
        "architecture": "arm64-v8a",
        "rootProfile": "rooted-lab",
        "lamdaVersion": lamda,
        "lamdaChannel": "stable",
        "app": {
            "packageName": "com.example.target",
            "version": app_version,
            "signatureSha256": SHA_B,
        },
    }


def observation(
    prefix: str,
    started_at: str,
    completed_at: str,
    *,
    outcome: str = "PASS",
    duration_ms: int = 1000,
) -> dict[str, Any]:
    return {
        "sampleId": f"sample-{prefix}",
        "correlationId": f"correlation-{prefix}",
        "startedAt": started_at,
        "completedAt": completed_at,
        "outcome": outcome,
        "durationMs": duration_ms,
        "safetyViolations": 0,
        "evidenceRefs": ["external-results.log"],
    }


def common_bundle(root: Path, task_id: str) -> dict[str, Any]:
    evidence = root / "external-results.log"
    evidence.write_text("authorized external hardware results\n", encoding="utf-8")
    digest = hashlib.sha256(evidence.read_bytes()).hexdigest()
    return {
        "schemaVersion": "1.0",
        "taskId": task_id,
        "evidenceClass": "EXTERNAL_AUTHORIZED_HARDWARE",
        "executionMode": "REAL_DEVICE",
        "hardwareEvidence": True,
        "authorization": {
            "status": "APPROVED",
            "ticket": "SEC-2026-0831",
            "approvedBy": "security@example.test",
            "approvedAt": "2026-08-27T00:00:00+00:00",
            "expiresAt": "2026-09-01T00:00:00+00:00",
        },
        "automationPackage": {
            "name": "publisher",
            "version": "2.0.0",
            "artifactSha256": SHA_D,
        },
        "evidenceFiles": [{"path": "external-results.log", "sha256": digest}],
    }


def rollback() -> dict[str, Any]:
    return {
        "tested": True,
        "outcome": "PASS",
        "startedAt": "2026-08-30T04:00:00+00:00",
        "completedAt": "2026-08-30T04:30:00+00:00",
        "restoredVersion": "1.0.0",
        "artifactSha256": SHA_C,
        "procedureRefs": ["external-results.log"],
        "evidenceRefs": ["external-results.log"],
    }


def compatibility_bundle(root: Path) -> dict[str, Any]:
    bundle = common_bundle(root, "P5-003")
    bundle["coverage"] = {
        "androidVersions": ["14"],
        "lamdaVersions": ["10.8"],
        "appReleases": {"N": "8.32.1", "N-1": "8.31.0"},
        "minimumSamplesPerTrack": 2,
        "minimumSoakHours": 72,
        "maxCandidateFailureRate": 0.1,
        "maxFailureRateRegression": 0.05,
    }
    cells: list[dict[str, Any]] = []
    for release_level, app_version in (("N", "8.32.1"), ("N-1", "8.31.0")):
        prefix = release_level.replace("-", "m")
        cells.append(
            {
                "cellId": f"android14-lamda10.8-{release_level}",
                "appRelease": release_level,
                "environment": environment(app_version=app_version),
                "stable": {
                    "automationVersion": "1.0.0",
                    "artifactSha256": SHA_C,
                    "samples": [
                        observation(
                            f"{prefix}-stable-1",
                            "2026-08-27T01:00:00+00:00",
                            "2026-08-27T01:01:00+00:00",
                        ),
                        observation(
                            f"{prefix}-stable-2",
                            "2026-08-30T02:00:00+00:00",
                            "2026-08-30T02:01:00+00:00",
                        ),
                    ],
                    "evidenceRefs": ["external-results.log"],
                },
                "candidate": {
                    "automationVersion": "2.0.0",
                    "artifactSha256": SHA_D,
                    "samples": [
                        observation(
                            f"{prefix}-candidate-1",
                            "2026-08-27T01:00:00+00:00",
                            "2026-08-27T01:01:00+00:00",
                        ),
                        observation(
                            f"{prefix}-candidate-2",
                            "2026-08-30T02:00:00+00:00",
                            "2026-08-30T02:01:00+00:00",
                        ),
                    ],
                    "evidenceRefs": ["external-results.log"],
                },
                "rollback": rollback(),
            }
        )
    bundle["matrix"] = cells
    bundle["promotion"] = {
        "requested": True,
        "decision": "PROMOTE",
        "reviewedBy": "release@example.test",
        "reviewedAt": "2026-08-30T06:00:00+00:00",
        "evidenceRefs": ["external-results.log"],
    }
    return bundle


def dual_track_bundle(root: Path) -> dict[str, Any]:
    bundle = common_bundle(root, "P5-006")
    bundle["policy"] = {
        "minimumPairs": 2,
        "maxCandidateFailureRate": 0.1,
        "maxOutcomeRegressionRate": 0.1,
        "maxP95DurationRegressionRatio": 1.25,
    }
    pairs: list[dict[str, Any]] = []
    for index in range(2):
        scenario = f"publish-{index}"
        input_sha = hashlib.sha256(scenario.encode()).hexdigest()
        baseline = observation(
            f"dual-{index}-baseline",
            f"2026-08-30T0{index + 1}:00:00+00:00",
            f"2026-08-30T0{index + 1}:01:00+00:00",
            duration_ms=1000 + index,
        )
        baseline.update(
            {
                "engine": "AUTOJS",
                "scenarioId": scenario,
                "inputSha256": input_sha,
                "version": "6.5.0",
                "artifactSha256": SHA_C,
            }
        )
        candidate = observation(
            f"dual-{index}-candidate",
            f"2026-08-30T0{index + 1}:02:00+00:00",
            f"2026-08-30T0{index + 1}:03:00+00:00",
            duration_ms=1100 + index,
        )
        candidate.update(
            {
                "engine": "CLOUDCTL",
                "scenarioId": scenario,
                "inputSha256": input_sha,
                "version": "2.0.0",
                "artifactSha256": SHA_D,
            }
        )
        pairs.append(
            {
                "pairId": f"pair-{index}",
                "scenarioId": scenario,
                "inputSha256": input_sha,
                "environment": environment(),
                "baseline": baseline,
                "candidate": candidate,
            }
        )
    bundle["pairs"] = pairs
    bundle["rollback"] = rollback()
    bundle["comparison"] = {
        "decision": "MIGRATE",
        "reviewedBy": "migration@example.test",
        "reviewedAt": "2026-08-30T06:00:00+00:00",
        "evidenceRefs": ["external-results.log"],
    }
    return bundle


def production_bundle(root: Path) -> dict[str, Any]:
    bundle = common_bundle(root, "P5-007")
    bundle["policy"] = {
        "maximumCanaryPercentage": 5,
        "minimumSamples": 2,
        "minimumObservationHours": 1,
        "maxCandidateFailureRate": 0.1,
        "maxFailureRateRegression": 0.05,
    }
    bundle["release"] = {
        "releaseId": "release-2026-0831",
        "stableVersion": "1.0.0",
        "candidateVersion": "2.0.0",
        "artifactSha256": SHA_D,
        "commitIntentId": "intent-release-2026-0831",
    }
    bundle["gates"] = [
        {"id": gate_id, "status": "PASS", "evidenceRefs": ["external-results.log"]}
        for gate_id in sorted(load_module().REQUIRED_RELEASE_GATES)
    ]
    first = observation(
        "canary-1",
        "2026-08-30T01:00:00+00:00",
        "2026-08-30T01:01:00+00:00",
    )
    first.update(
        {
            "deviceSerialHash": SHA_A,
            "commitStatus": "COMMITTED",
            "auditComplete": True,
            "irreversibleAction": True,
            "commitIntentId": "intent-release-2026-0831",
            "irreversibleActionId": "publish-1",
        }
    )
    second = observation(
        "canary-2",
        "2026-08-30T02:30:00+00:00",
        "2026-08-30T02:31:00+00:00",
    )
    second.update(
        {
            "deviceSerialHash": SHA_B,
            "commitStatus": "NOT_APPLICABLE",
            "auditComplete": True,
            "irreversibleAction": False,
        }
    )
    bundle["canary"] = {
        "eligiblePopulation": 40,
        "selectedCount": 2,
        "declaredPercentage": 5,
        "stableFailureRate": 0,
        "cohort": [environment(serial=SHA_A), environment(serial=SHA_B)],
        "observations": [first, second],
        "evidenceRefs": ["external-results.log"],
    }
    bundle["rollback"] = rollback()
    bundle["postmortem"] = {
        "completed": True,
        "reviewedBy": "release@example.test",
        "reviewedAt": "2026-08-30T06:00:00+00:00",
        "summary": "No safety or audit regressions observed.",
        "actionItems": [],
        "evidenceRefs": ["external-results.log"],
    }
    return bundle


def write_bundle(root: Path, bundle: dict[str, Any]) -> Path:
    path = root / "bundle.json"
    path.write_text(json.dumps(bundle), encoding="utf-8")
    return path


@pytest.mark.parametrize(
    ("factory", "task_id", "eligibility_key"),
    [
        (compatibility_bundle, "P5-003", "promotionEligible"),
        (dual_track_bundle, "P5-006", "migrationEligible"),
        (production_bundle, "P5-007", "releaseEligible"),
    ],
)
def test_valid_external_bundle_passes(
    tmp_path: Path,
    factory: Any,
    task_id: str,
    eligibility_key: str,
) -> None:
    result = load_module().validate_bundle(write_bundle(tmp_path, factory(tmp_path)), task_id)

    assert result["hardwareEvidence"] is True
    assert result["softwareValidation"] == "PASSED"
    assert result["result"][eligibility_key] is True


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("evidenceClass", "MOCK", "evidenceClass"),
        ("evidenceClass", "TEMPLATE", "evidenceClass"),
        ("executionMode", "DRY_RUN", "executionMode"),
        ("hardwareEvidence", False, "hardwareEvidence"),
    ],
)
def test_mock_template_and_dry_run_are_rejected(
    tmp_path: Path, field: str, value: object, message: str
) -> None:
    bundle = dual_track_bundle(tmp_path)
    bundle[field] = value

    with pytest.raises(ValueError, match=message):
        load_module().validate_bundle(write_bundle(tmp_path, bundle))


def test_execution_outside_authorization_is_rejected(tmp_path: Path) -> None:
    bundle = dual_track_bundle(tmp_path)
    bundle["authorization"]["expiresAt"] = "2026-08-30T01:30:00+00:00"

    with pytest.raises(ValueError, match="authorization window"):
        load_module().validate_bundle(write_bundle(tmp_path, bundle))


def test_emulator_is_rejected(tmp_path: Path) -> None:
    bundle = compatibility_bundle(tmp_path)
    bundle["matrix"][0]["environment"]["emulator"] = True

    with pytest.raises(ValueError, match="physical, non-emulator"):
        load_module().validate_bundle(write_bundle(tmp_path, bundle))


def test_bad_evidence_hash_is_rejected(tmp_path: Path) -> None:
    bundle = production_bundle(tmp_path)
    bundle["evidenceFiles"][0]["sha256"] = SHA_A

    with pytest.raises(ValueError, match="checksum mismatch"):
        load_module().validate_bundle(write_bundle(tmp_path, bundle))


def test_missing_matrix_coverage_is_rejected(tmp_path: Path) -> None:
    bundle = compatibility_bundle(tmp_path)
    bundle["matrix"].pop()

    with pytest.raises(ValueError, match="coverage is missing cells"):
        load_module().validate_bundle(write_bundle(tmp_path, bundle))


def test_insufficient_matrix_samples_are_rejected(tmp_path: Path) -> None:
    bundle = compatibility_bundle(tmp_path)
    bundle["matrix"][0]["candidate"]["samples"].pop()

    with pytest.raises(ValueError, match="insufficient samples"):
        load_module().validate_bundle(write_bundle(tmp_path, bundle))


def test_excess_candidate_failure_rate_is_rejected(tmp_path: Path) -> None:
    bundle = compatibility_bundle(tmp_path)
    bundle["matrix"][0]["candidate"]["samples"][0]["outcome"] = "FAIL"

    with pytest.raises(ValueError, match="failure rate exceeds"):
        load_module().validate_bundle(write_bundle(tmp_path, bundle))


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ({"safetyViolations": 1}, "safety violations"),
        ({"commitStatus": "UNKNOWN"}, "unknown commit"),
        ({"auditComplete": False}, "audit/evidence gaps"),
    ],
)
def test_canary_safety_unknown_commit_and_audit_gaps_are_rejected(
    tmp_path: Path, mutation: dict[str, Any], message: str
) -> None:
    bundle = production_bundle(tmp_path)
    bundle["canary"]["observations"][0].update(mutation)

    with pytest.raises(ValueError, match=message):
        load_module().validate_bundle(write_bundle(tmp_path, bundle))


@pytest.mark.parametrize(
    ("section", "message"),
    [("rollback", "rollback"), ("postmortem", "postmortem")],
)
def test_missing_rollback_or_postmortem_is_rejected(
    tmp_path: Path, section: str, message: str
) -> None:
    bundle = production_bundle(tmp_path)
    bundle.pop(section)

    with pytest.raises(ValueError, match=message):
        load_module().validate_bundle(write_bundle(tmp_path, bundle))


def test_canary_above_five_percent_is_rejected(tmp_path: Path) -> None:
    bundle = production_bundle(tmp_path)
    bundle["canary"]["eligiblePopulation"] = 30
    bundle["canary"]["declaredPercentage"] = 2 / 30 * 100

    with pytest.raises(ValueError, match="five-percent limit"):
        load_module().validate_bundle(write_bundle(tmp_path, bundle))


def test_dual_track_identity_and_rollback_are_enforced(tmp_path: Path) -> None:
    bundle = dual_track_bundle(tmp_path)
    bundle["pairs"][0]["candidate"]["scenarioId"] = "different-scenario"

    with pytest.raises(ValueError, match="scenario identity"):
        load_module().validate_bundle(write_bundle(tmp_path, bundle))

    bundle = dual_track_bundle(tmp_path)
    bundle["rollback"]["tested"] = False
    with pytest.raises(ValueError, match="tested, passing rollback"):
        load_module().validate_bundle(write_bundle(tmp_path, bundle))


def test_secret_material_is_rejected(tmp_path: Path) -> None:
    bundle = production_bundle(tmp_path)
    bundle["postmortem"]["summary"] = "-----BEGIN " + "PRIVATE KEY-----"

    with pytest.raises(ValueError, match="secret or private-key material"):
        load_module().validate_bundle(write_bundle(tmp_path, bundle))


def test_secret_material_inside_evidence_file_is_rejected(tmp_path: Path) -> None:
    bundle = production_bundle(tmp_path)
    evidence = tmp_path / "external-results.log"
    evidence.write_text("password=" + "not-a-real-secret", encoding="utf-8")
    bundle["evidenceFiles"][0]["sha256"] = hashlib.sha256(evidence.read_bytes()).hexdigest()

    with pytest.raises(ValueError, match="secret or private-key material"):
        load_module().validate_bundle(write_bundle(tmp_path, bundle))


@pytest.mark.parametrize("filename", ["mock-results.log", "dry-run-results.log", "template.json"])
def test_non_external_evidence_paths_are_rejected(tmp_path: Path, filename: str) -> None:
    bundle = production_bundle(tmp_path)
    source = tmp_path / "external-results.log"
    target = tmp_path / filename
    target.write_bytes(source.read_bytes())
    bundle["evidenceFiles"][0]["path"] = filename

    with pytest.raises(ValueError, match="mock, template, dry-run or synthetic"):
        load_module().validate_bundle(write_bundle(tmp_path, bundle))


def test_machine_readable_contracts_cover_all_tasks() -> None:
    module = load_module()
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))

    assert set(module.TASK_CONTRACTS) == {"P5-003", "P5-006", "P5-007"}
    assert module.TASK_CONTRACTS["P5-003"]["minimumSoakHours"] == 72
    assert module.TASK_CONTRACTS["P5-007"]["maximumCanaryPercentage"] == 5
    assert set(contract["tasks"]) == set(module.TASK_CONTRACTS)
    assert contract["common"]["constants"]["hardwareEvidence"] is True
