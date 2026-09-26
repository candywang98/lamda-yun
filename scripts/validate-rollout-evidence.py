#!/usr/bin/env python3
"""Validate external hardware evidence for compatibility and rollout tasks."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Any

SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
PRIVATE_KEY_PATTERN = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----", re.IGNORECASE)
SECRET_ASSIGNMENT_PATTERN = re.compile(
    r"(?:password|api[_-]?key|access[_-]?token|client[_-]?secret)\s*[:=]\s*\S+",
    re.IGNORECASE,
)
BEARER_PATTERN = re.compile(r"authorization\s*:\s*bearer\s+\S+", re.IGNORECASE)
NON_EXTERNAL_PATH_PATTERN = re.compile(
    r"(?:^|[._ -])"
    r"(?:mock|template|dry[ _-]?run|synthetic|simulator|emulator|local[ _-]?only)"
    r"(?:$|[._ -])",
    re.IGNORECASE,
)

SUPPORTED_TASKS = {"P5-003", "P5-006", "P5-007"}
EXTERNAL_EVIDENCE_CLASS = "EXTERNAL_AUTHORIZED_HARDWARE"
REAL_EXECUTION_MODE = "REAL_DEVICE"
REQUIRED_RELEASE_GATES = {
    "artifact.verified",
    "authorization.approved",
    "compatibility.approved",
    "observability.ready",
    "rollback.ready",
    "support.ready",
}

TASK_CONTRACTS: dict[str, dict[str, Any]] = {
    "P5-003": {
        "purpose": "Android/LAMDA/App compatibility matrix and candidate promotion",
        "requiredSections": ["coverage", "matrix", "promotion"],
        "minimumSoakHours": 72,
        "requiredAppReleaseLevels": ["N", "N-1"],
    },
    "P5-006": {
        "purpose": "paired AutoJS baseline and CloudCtl candidate comparison",
        "requiredSections": ["policy", "pairs", "rollback", "comparison"],
        "pairedIdentity": ["scenarioId", "inputSha256"],
    },
    "P5-007": {
        "purpose": "production gates, five-percent canary, rollback and review",
        "requiredSections": ["policy", "release", "gates", "canary", "rollback", "postmortem"],
        "maximumCanaryPercentage": 5,
        "requiredReleaseGates": sorted(REQUIRED_RELEASE_GATES),
    },
}


class EvidenceError(ValueError):
    """Raised when an evidence bundle cannot prove the requested acceptance gate."""


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
    return value.strip()


def _integer(value: Any, field: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise EvidenceError(f"{field} must be an integer >= {minimum}")
    return value


def _number(value: Any, field: str, *, minimum: float = 0) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise EvidenceError(f"{field} must be a number")
    result = float(value)
    if not math.isfinite(result) or result < minimum:
        raise EvidenceError(f"{field} must be a finite number >= {minimum}")
    return result


def _rate(value: Any, field: str) -> float:
    result = _number(value, field)
    if result > 1:
        raise EvidenceError(f"{field} must be between 0 and 1")
    return result


def _timestamp(value: Any, field: str) -> datetime:
    raw = _text(value, field)
    try:
        result = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EvidenceError(f"{field} must be an ISO-8601 timestamp") from exc
    if result.tzinfo is None:
        raise EvidenceError(f"{field} must include a timezone")
    return result


def _digest(value: Any, field: str) -> str:
    result = _text(value, field).lower()
    if not SHA256_PATTERN.fullmatch(result):
        raise EvidenceError(f"{field} must be a lowercase SHA256 digest")
    return result


def _reject_secrets(value: Any, field: str = "bundle") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            _reject_secrets(child, f"{field}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_secrets(child, f"{field}[{index}]")
    elif isinstance(value, str) and any(
        pattern.search(value)
        for pattern in (PRIVATE_KEY_PATTERN, SECRET_ASSIGNMENT_PATTERN, BEARER_PATTERN)
    ):
        raise EvidenceError(f"{field} contains secret or private-key material")


def _reject_non_external_path(value: str, field: str) -> None:
    if NON_EXTERNAL_PATH_PATTERN.search(value):
        raise EvidenceError(f"{field} identifies mock, template, dry-run or synthetic evidence")


def _evidence_file(root: Path, raw_path: Any) -> Path:
    relative = Path(_text(raw_path, "evidenceFiles.path"))
    _reject_non_external_path(relative.as_posix(), "evidenceFiles.path")
    if relative.is_absolute() or ".." in relative.parts:
        raise EvidenceError("evidence file paths must stay beside the evidence bundle")
    resolved_root = root.resolve()
    resolved = (root / relative).resolve()
    if resolved_root not in resolved.parents:
        raise EvidenceError("evidence file paths must stay beside the evidence bundle")
    if not resolved.is_file():
        raise EvidenceError(f"evidence file does not exist: {relative.as_posix()}")
    return resolved


def _evidence_refs(value: Any, field: str, files: set[str]) -> list[str]:
    refs = [_text(item, f"{field}[]") for item in _list(value, field)]
    if not refs:
        raise EvidenceError(f"{field} cannot be empty")
    if len(set(refs)) != len(refs):
        raise EvidenceError(f"{field} contains duplicate references")
    missing = sorted(set(refs) - files)
    if missing:
        raise EvidenceError(f"{field} references missing evidence files: {missing}")
    return refs


def _inside_window(
    started: Any,
    completed: Any,
    field: str,
    approved_at: datetime,
    expires_at: datetime,
) -> tuple[datetime, datetime]:
    started_at = _timestamp(started, f"{field}.startedAt")
    completed_at = _timestamp(completed, f"{field}.completedAt")
    if not (approved_at <= started_at <= completed_at <= expires_at):
        raise EvidenceError(f"{field} must execute inside the authorization window")
    return started_at, completed_at


def _validate_environment(value: Any, field: str) -> dict[str, str]:
    environment = _mapping(value, field)
    if environment.get("physical") is not True or environment.get("emulator") is not False:
        raise EvidenceError(f"{field} must identify a physical, non-emulator device")
    app = _mapping(environment.get("app"), f"{field}.app")
    return {
        "serialHash": _digest(environment.get("serialHash"), f"{field}.serialHash"),
        "model": _text(environment.get("model"), f"{field}.model"),
        "androidVersion": _text(environment.get("androidVersion"), f"{field}.androidVersion"),
        "architecture": _text(environment.get("architecture"), f"{field}.architecture"),
        "rootProfile": _text(environment.get("rootProfile"), f"{field}.rootProfile"),
        "lamdaVersion": _text(environment.get("lamdaVersion"), f"{field}.lamdaVersion"),
        "lamdaChannel": _text(environment.get("lamdaChannel"), f"{field}.lamdaChannel"),
        "appPackage": _text(app.get("packageName"), f"{field}.app.packageName"),
        "appVersion": _text(app.get("version"), f"{field}.app.version"),
        "appSignature": _digest(app.get("signatureSha256"), f"{field}.app.signatureSha256"),
    }


def _validate_observation(
    value: Any,
    field: str,
    context: dict[str, Any],
    *,
    allowed_outcomes: set[str] | None = None,
) -> dict[str, Any]:
    observation = _mapping(value, field)
    sample_id = _text(observation.get("sampleId"), f"{field}.sampleId")
    correlation_id = _text(observation.get("correlationId"), f"{field}.correlationId")
    for identifier, collection, name in (
        (sample_id, context["sampleIds"], "sampleId"),
        (correlation_id, context["correlationIds"], "correlationId"),
    ):
        if identifier in collection:
            raise EvidenceError(f"duplicate {name}: {identifier}")
        collection.add(identifier)
    started_at, completed_at = _inside_window(
        observation.get("startedAt"),
        observation.get("completedAt"),
        field,
        context["approvedAt"],
        context["expiresAt"],
    )
    outcome = _text(observation.get("outcome"), f"{field}.outcome")
    accepted_outcomes = allowed_outcomes or {"PASS", "FAIL", "UNKNOWN_COMMIT"}
    if outcome not in accepted_outcomes:
        raise EvidenceError(f"{field}.outcome must be one of {sorted(accepted_outcomes)}")
    duration_ms = _integer(observation.get("durationMs"), f"{field}.durationMs", minimum=1)
    safety_violations = _integer(observation.get("safetyViolations"), f"{field}.safetyViolations")
    _evidence_refs(observation.get("evidenceRefs"), f"{field}.evidenceRefs", context["files"])
    return {
        "sampleId": sample_id,
        "correlationId": correlation_id,
        "startedAt": started_at,
        "completedAt": completed_at,
        "outcome": outcome,
        "durationMs": duration_ms,
        "safetyViolations": safety_violations,
        "unknownCommit": outcome == "UNKNOWN_COMMIT",
    }


def _validate_rollback(value: Any, field: str, context: dict[str, Any]) -> dict[str, Any]:
    rollback = _mapping(value, field)
    if rollback.get("tested") is not True or rollback.get("outcome") != "PASS":
        raise EvidenceError(f"{field} must contain a tested, passing rollback")
    started_at, completed_at = _inside_window(
        rollback.get("startedAt"),
        rollback.get("completedAt"),
        field,
        context["approvedAt"],
        context["expiresAt"],
    )
    _text(rollback.get("restoredVersion"), f"{field}.restoredVersion")
    _digest(rollback.get("artifactSha256"), f"{field}.artifactSha256")
    _evidence_refs(rollback.get("procedureRefs"), f"{field}.procedureRefs", context["files"])
    _evidence_refs(rollback.get("evidenceRefs"), f"{field}.evidenceRefs", context["files"])
    return {"startedAt": started_at, "completedAt": completed_at}


def _validate_common(
    bundle_path: Path, expected_task_id: str | None
) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        _reject_non_external_path(bundle_path.name, "bundle path")
        bundle = _mapping(json.loads(bundle_path.read_text(encoding="utf-8")), "bundle")
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"cannot read evidence bundle: {exc}") from exc
    _reject_secrets(bundle)
    if bundle.get("schemaVersion") != "1.0":
        raise EvidenceError("schemaVersion must be 1.0")
    task_id = _text(bundle.get("taskId"), "taskId")
    if task_id not in SUPPORTED_TASKS:
        raise EvidenceError(f"unsupported rollout task: {task_id}")
    if expected_task_id is not None and task_id != expected_task_id:
        raise EvidenceError(f"bundle taskId {task_id} does not match {expected_task_id}")
    if bundle.get("evidenceClass") != EXTERNAL_EVIDENCE_CLASS:
        raise EvidenceError("evidenceClass must be EXTERNAL_AUTHORIZED_HARDWARE")
    if bundle.get("executionMode") != REAL_EXECUTION_MODE:
        raise EvidenceError("executionMode must be REAL_DEVICE; mock, template and dry-run fail")
    if bundle.get("hardwareEvidence") is not True:
        raise EvidenceError("hardwareEvidence must be true for candidate acceptance")

    authorization = _mapping(bundle.get("authorization"), "authorization")
    if authorization.get("status") != "APPROVED":
        raise EvidenceError("authorization.status must be APPROVED")
    _text(authorization.get("ticket"), "authorization.ticket")
    _text(authorization.get("approvedBy"), "authorization.approvedBy")
    approved_at = _timestamp(authorization.get("approvedAt"), "authorization.approvedAt")
    expires_at = _timestamp(authorization.get("expiresAt"), "authorization.expiresAt")
    if expires_at <= approved_at:
        raise EvidenceError("authorization must expire after approval")

    package = _mapping(bundle.get("automationPackage"), "automationPackage")
    package_name = _text(package.get("name"), "automationPackage.name")
    package_version = _text(package.get("version"), "automationPackage.version")
    package_sha = _digest(package.get("artifactSha256"), "automationPackage.artifactSha256")

    files: set[str] = set()
    for index, raw_entry in enumerate(_list(bundle.get("evidenceFiles"), "evidenceFiles")):
        entry = _mapping(raw_entry, f"evidenceFiles[{index}]")
        relative = _text(entry.get("path"), f"evidenceFiles[{index}].path")
        if relative in files:
            raise EvidenceError(f"duplicate evidence file: {relative}")
        evidence_path = _evidence_file(bundle_path.parent, relative)
        evidence_bytes = evidence_path.read_bytes()
        _reject_secrets(evidence_bytes.decode("utf-8", errors="ignore"), relative)
        actual = hashlib.sha256(evidence_bytes).hexdigest()
        expected = _digest(entry.get("sha256"), f"evidenceFiles[{index}].sha256")
        if actual != expected:
            raise EvidenceError(f"evidence checksum mismatch: {relative}")
        files.add(relative)
    if not files:
        raise EvidenceError("evidenceFiles cannot be empty")

    context: dict[str, Any] = {
        "taskId": task_id,
        "approvedAt": approved_at,
        "expiresAt": expires_at,
        "files": files,
        "sampleIds": set(),
        "correlationIds": set(),
        "packageName": package_name,
        "packageVersion": package_version,
        "packageSha256": package_sha,
    }
    return bundle, context


def _failure_rate(observations: list[dict[str, Any]]) -> float:
    return sum(item["outcome"] != "PASS" for item in observations) / len(observations)


def _p95(values: list[int]) -> int:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * 0.95) - 1)]


def validate_compatibility_matrix(
    bundle: dict[str, Any], context: dict[str, Any]
) -> dict[str, Any]:
    coverage = _mapping(bundle.get("coverage"), "coverage")
    android_versions = {
        _text(item, "coverage.androidVersions[]")
        for item in _list(coverage.get("androidVersions"), "coverage.androidVersions")
    }
    lamda_versions = {
        _text(item, "coverage.lamdaVersions[]")
        for item in _list(coverage.get("lamdaVersions"), "coverage.lamdaVersions")
    }
    releases = _mapping(coverage.get("appReleases"), "coverage.appReleases")
    if set(releases) != {"N", "N-1"}:
        raise EvidenceError("coverage.appReleases must declare exactly N and N-1")
    app_versions = {
        level: _text(version, f"coverage.appReleases.{level}")
        for level, version in releases.items()
    }
    if len(set(app_versions.values())) != 2:
        raise EvidenceError("N and N-1 must identify different App versions")
    if not android_versions or not lamda_versions:
        raise EvidenceError("Android and LAMDA coverage cannot be empty")
    minimum_samples = _integer(
        coverage.get("minimumSamplesPerTrack"), "coverage.minimumSamplesPerTrack", minimum=1
    )
    minimum_soak_hours = _number(
        coverage.get("minimumSoakHours"), "coverage.minimumSoakHours", minimum=72
    )
    max_failure_rate = _rate(
        coverage.get("maxCandidateFailureRate"), "coverage.maxCandidateFailureRate"
    )
    max_regression = _rate(
        coverage.get("maxFailureRateRegression"), "coverage.maxFailureRateRegression"
    )

    expected_cells = {
        (android, lamda, level)
        for android in android_versions
        for lamda in lamda_versions
        for level in app_versions
    }
    observed_cells: set[tuple[str, str, str]] = set()
    cell_ids: set[str] = set()
    latest_completion = context["approvedAt"]
    for index, raw_cell in enumerate(_list(bundle.get("matrix"), "matrix")):
        field = f"matrix[{index}]"
        cell = _mapping(raw_cell, field)
        cell_id = _text(cell.get("cellId"), f"{field}.cellId")
        if cell_id in cell_ids:
            raise EvidenceError(f"duplicate compatibility cellId: {cell_id}")
        cell_ids.add(cell_id)
        environment = _validate_environment(cell.get("environment"), f"{field}.environment")
        release_level = _text(cell.get("appRelease"), f"{field}.appRelease")
        if release_level not in app_versions:
            raise EvidenceError(f"{field}.appRelease is outside the declared N/N-1 coverage")
        if environment["appVersion"] != app_versions[release_level]:
            raise EvidenceError(f"{field} App version does not match its release level")
        cell_key = (
            environment["androidVersion"],
            environment["lamdaVersion"],
            release_level,
        )
        if cell_key in observed_cells:
            raise EvidenceError(f"duplicate compatibility matrix cell: {cell_key}")
        observed_cells.add(cell_key)

        track_results: dict[str, list[dict[str, Any]]] = {}
        for track_name in ("stable", "candidate"):
            track_field = f"{field}.{track_name}"
            track = _mapping(cell.get(track_name), track_field)
            _text(track.get("automationVersion"), f"{track_field}.automationVersion")
            track_sha = _digest(track.get("artifactSha256"), f"{track_field}.artifactSha256")
            if track_name == "candidate" and track_sha != context["packageSha256"]:
                raise EvidenceError("candidate artifact does not match automationPackage")
            observations = [
                _validate_observation(item, f"{track_field}.samples[{sample_index}]", context)
                for sample_index, item in enumerate(
                    _list(track.get("samples"), f"{track_field}.samples")
                )
            ]
            if len(observations) < minimum_samples:
                raise EvidenceError(f"{track_field} has insufficient samples")
            if any(item["safetyViolations"] for item in observations):
                raise EvidenceError(f"{track_field} contains safety violations")
            if any(item["unknownCommit"] for item in observations):
                raise EvidenceError(f"{track_field} contains an unknown commit")
            _evidence_refs(
                track.get("evidenceRefs"),
                f"{track_field}.evidenceRefs",
                context["files"],
            )
            track_results[track_name] = observations
            latest_completion = max(
                latest_completion, max(item["completedAt"] for item in observations)
            )

        stable_rate = _failure_rate(track_results["stable"])
        candidate_rate = _failure_rate(track_results["candidate"])
        if candidate_rate > max_failure_rate:
            raise EvidenceError(f"{field} candidate failure rate exceeds threshold")
        if candidate_rate - stable_rate > max_regression:
            raise EvidenceError(f"{field} candidate failure regression exceeds threshold")
        candidate_start = min(item["startedAt"] for item in track_results["candidate"])
        candidate_end = max(item["completedAt"] for item in track_results["candidate"])
        soak_hours = (candidate_end - candidate_start).total_seconds() / 3600
        if soak_hours < minimum_soak_hours:
            raise EvidenceError(f"{field} candidate soak duration is below {minimum_soak_hours}h")
        _validate_rollback(cell.get("rollback"), f"{field}.rollback", context)

    missing_cells = sorted(expected_cells - observed_cells)
    if missing_cells:
        raise EvidenceError(f"compatibility matrix coverage is missing cells: {missing_cells}")
    unexpected_cells = sorted(observed_cells - expected_cells)
    if unexpected_cells:
        raise EvidenceError(f"compatibility matrix contains undeclared cells: {unexpected_cells}")

    promotion = _mapping(bundle.get("promotion"), "promotion")
    if promotion.get("requested") is not True or promotion.get("decision") != "PROMOTE":
        raise EvidenceError("promotion must explicitly request and approve PROMOTE")
    _text(promotion.get("reviewedBy"), "promotion.reviewedBy")
    reviewed_at = _timestamp(promotion.get("reviewedAt"), "promotion.reviewedAt")
    if not (latest_completion <= reviewed_at <= context["expiresAt"]):
        raise EvidenceError("promotion review must follow all runs inside authorization")
    _evidence_refs(promotion.get("evidenceRefs"), "promotion.evidenceRefs", context["files"])
    return {
        "coveredCells": len(observed_cells),
        "requiredCells": len(expected_cells),
        "minimumSoakHours": minimum_soak_hours,
        "promotionEligible": True,
    }


def validate_dual_track_comparison(
    bundle: dict[str, Any], context: dict[str, Any]
) -> dict[str, Any]:
    policy = _mapping(bundle.get("policy"), "policy")
    minimum_pairs = _integer(policy.get("minimumPairs"), "policy.minimumPairs", minimum=1)
    max_candidate_failure = _rate(
        policy.get("maxCandidateFailureRate"), "policy.maxCandidateFailureRate"
    )
    max_regression = _rate(
        policy.get("maxOutcomeRegressionRate"), "policy.maxOutcomeRegressionRate"
    )
    max_duration_ratio = _number(
        policy.get("maxP95DurationRegressionRatio"),
        "policy.maxP95DurationRegressionRatio",
        minimum=1,
    )
    pairs = _list(bundle.get("pairs"), "pairs")
    if len(pairs) < minimum_pairs:
        raise EvidenceError("dual-track comparison has insufficient paired samples")
    pair_ids: set[str] = set()
    baseline_results: list[dict[str, Any]] = []
    candidate_results: list[dict[str, Any]] = []
    latest_completion = context["approvedAt"]
    regressions = 0
    for index, raw_pair in enumerate(pairs):
        field = f"pairs[{index}]"
        pair = _mapping(raw_pair, field)
        pair_id = _text(pair.get("pairId"), f"{field}.pairId")
        if pair_id in pair_ids:
            raise EvidenceError(f"duplicate pairId: {pair_id}")
        pair_ids.add(pair_id)
        scenario_id = _text(pair.get("scenarioId"), f"{field}.scenarioId")
        input_sha = _digest(pair.get("inputSha256"), f"{field}.inputSha256")
        _validate_environment(pair.get("environment"), f"{field}.environment")

        results: dict[str, dict[str, Any]] = {}
        for track_name, engine in (("baseline", "AUTOJS"), ("candidate", "CLOUDCTL")):
            track_field = f"{field}.{track_name}"
            track = _mapping(pair.get(track_name), track_field)
            if track.get("engine") != engine:
                raise EvidenceError(f"{track_field}.engine must be {engine}")
            if _text(track.get("scenarioId"), f"{track_field}.scenarioId") != scenario_id:
                raise EvidenceError(f"{track_field} scenario identity does not match the pair")
            if _digest(track.get("inputSha256"), f"{track_field}.inputSha256") != input_sha:
                raise EvidenceError(f"{track_field} input identity does not match the pair")
            _text(track.get("version"), f"{track_field}.version")
            artifact_sha = _digest(track.get("artifactSha256"), f"{track_field}.artifactSha256")
            if track_name == "candidate" and artifact_sha != context["packageSha256"]:
                raise EvidenceError("CloudCtl candidate artifact does not match automationPackage")
            result = _validate_observation(track, track_field, context)
            if result["safetyViolations"]:
                raise EvidenceError(f"{track_field} contains safety violations")
            if result["unknownCommit"]:
                raise EvidenceError(f"{track_field} contains an unknown commit")
            results[track_name] = result
            latest_completion = max(latest_completion, result["completedAt"])
        baseline_results.append(results["baseline"])
        candidate_results.append(results["candidate"])
        if results["baseline"]["outcome"] == "PASS" and results["candidate"]["outcome"] != "PASS":
            regressions += 1

    candidate_failure = _failure_rate(candidate_results)
    regression_rate = regressions / len(pairs)
    baseline_p95 = _p95([item["durationMs"] for item in baseline_results])
    candidate_p95 = _p95([item["durationMs"] for item in candidate_results])
    duration_ratio = candidate_p95 / baseline_p95
    if candidate_failure > max_candidate_failure:
        raise EvidenceError("CloudCtl candidate failure rate exceeds threshold")
    if regression_rate > max_regression:
        raise EvidenceError("CloudCtl candidate outcome regression exceeds threshold")
    if duration_ratio > max_duration_ratio:
        raise EvidenceError("CloudCtl candidate p95 duration regression exceeds threshold")
    _validate_rollback(bundle.get("rollback"), "rollback", context)

    comparison = _mapping(bundle.get("comparison"), "comparison")
    if comparison.get("decision") != "MIGRATE":
        raise EvidenceError("comparison.decision must be MIGRATE")
    _text(comparison.get("reviewedBy"), "comparison.reviewedBy")
    reviewed_at = _timestamp(comparison.get("reviewedAt"), "comparison.reviewedAt")
    if not (latest_completion <= reviewed_at <= context["expiresAt"]):
        raise EvidenceError("comparison review must follow paired runs inside authorization")
    _evidence_refs(comparison.get("evidenceRefs"), "comparison.evidenceRefs", context["files"])
    return {
        "pairedSamples": len(pairs),
        "candidateFailureRate": candidate_failure,
        "outcomeRegressionRate": regression_rate,
        "baselineP95DurationMs": baseline_p95,
        "candidateP95DurationMs": candidate_p95,
        "durationRegressionRatio": duration_ratio,
        "migrationEligible": True,
    }


def validate_production_canary(bundle: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    policy = _mapping(bundle.get("policy"), "policy")
    maximum_percentage = _number(
        policy.get("maximumCanaryPercentage"), "policy.maximumCanaryPercentage"
    )
    if maximum_percentage > 5:
        raise EvidenceError("policy.maximumCanaryPercentage cannot exceed 5")
    minimum_samples = _integer(policy.get("minimumSamples"), "policy.minimumSamples", minimum=1)
    minimum_hours = _number(
        policy.get("minimumObservationHours"), "policy.minimumObservationHours", minimum=1
    )
    max_failure_rate = _rate(
        policy.get("maxCandidateFailureRate"), "policy.maxCandidateFailureRate"
    )
    max_regression = _rate(
        policy.get("maxFailureRateRegression"), "policy.maxFailureRateRegression"
    )

    release = _mapping(bundle.get("release"), "release")
    _text(release.get("releaseId"), "release.releaseId")
    stable_version = _text(release.get("stableVersion"), "release.stableVersion")
    _text(release.get("candidateVersion"), "release.candidateVersion")
    if _digest(release.get("artifactSha256"), "release.artifactSha256") != context["packageSha256"]:
        raise EvidenceError("release artifact does not match automationPackage")
    commit_intent_id = _text(release.get("commitIntentId"), "release.commitIntentId")

    observed_gates: set[str] = set()
    for index, raw_gate in enumerate(_list(bundle.get("gates"), "gates")):
        field = f"gates[{index}]"
        gate = _mapping(raw_gate, field)
        gate_id = _text(gate.get("id"), f"{field}.id")
        if gate_id in observed_gates:
            raise EvidenceError(f"duplicate release gate: {gate_id}")
        if gate.get("status") != "PASS":
            raise EvidenceError(f"release gate did not pass: {gate_id}")
        _evidence_refs(gate.get("evidenceRefs"), f"{field}.evidenceRefs", context["files"])
        observed_gates.add(gate_id)
    missing_gates = sorted(REQUIRED_RELEASE_GATES - observed_gates)
    if missing_gates:
        raise EvidenceError(f"required release gates are missing: {missing_gates}")

    canary = _mapping(bundle.get("canary"), "canary")
    eligible_population = _integer(
        canary.get("eligiblePopulation"), "canary.eligiblePopulation", minimum=1
    )
    selected_count = _integer(canary.get("selectedCount"), "canary.selectedCount", minimum=1)
    computed_percentage = selected_count / eligible_population * 100
    declared_percentage = _number(canary.get("declaredPercentage"), "canary.declaredPercentage")
    if not math.isclose(computed_percentage, declared_percentage, abs_tol=0.000001):
        raise EvidenceError("canary.declaredPercentage does not match cohort counts")
    if computed_percentage > maximum_percentage or computed_percentage > 5:
        raise EvidenceError("canary cohort exceeds the five-percent limit")
    stable_failure_rate = _rate(canary.get("stableFailureRate"), "canary.stableFailureRate")

    cohort_serials: set[str] = set()
    for index, raw_environment in enumerate(_list(canary.get("cohort"), "canary.cohort")):
        environment = _validate_environment(raw_environment, f"canary.cohort[{index}]")
        serial_hash = environment["serialHash"]
        if serial_hash in cohort_serials:
            raise EvidenceError(f"duplicate canary device serialHash: {serial_hash}")
        cohort_serials.add(serial_hash)
    if len(cohort_serials) != selected_count:
        raise EvidenceError("canary cohort size must equal selectedCount")

    observations: list[dict[str, Any]] = []
    irreversible_actions: set[str] = set()
    audit_gaps = 0
    unknown_commits = 0
    safety_violations = 0
    for index, raw_observation in enumerate(
        _list(canary.get("observations"), "canary.observations")
    ):
        field = f"canary.observations[{index}]"
        observation_value = _mapping(raw_observation, field)
        serial_hash = _digest(
            observation_value.get("deviceSerialHash"), f"{field}.deviceSerialHash"
        )
        if serial_hash not in cohort_serials:
            raise EvidenceError(f"{field} references a device outside the canary cohort")
        result = _validate_observation(observation_value, field, context)
        commit_status = _text(observation_value.get("commitStatus"), f"{field}.commitStatus")
        if commit_status not in {"COMMITTED", "NOT_APPLICABLE", "UNKNOWN"}:
            raise EvidenceError(f"{field}.commitStatus is invalid")
        if commit_status == "UNKNOWN" or result["unknownCommit"]:
            unknown_commits += 1
        if observation_value.get("auditComplete") is not True:
            audit_gaps += 1
        if observation_value.get("irreversibleAction") is True:
            observed_intent = _text(
                observation_value.get("commitIntentId"), f"{field}.commitIntentId"
            )
            if observed_intent != commit_intent_id:
                raise EvidenceError(f"{field} commit intent does not match the release")
            action_id = _text(
                observation_value.get("irreversibleActionId"),
                f"{field}.irreversibleActionId",
            )
            if action_id in irreversible_actions:
                raise EvidenceError(f"duplicate irreversible action: {action_id}")
            irreversible_actions.add(action_id)
        observations.append(result)
        safety_violations += result["safetyViolations"]
    if len(observations) < minimum_samples:
        raise EvidenceError("production canary has insufficient samples")
    if safety_violations:
        raise EvidenceError("production canary contains safety violations")
    if unknown_commits:
        raise EvidenceError("production canary contains an unknown commit")
    if audit_gaps:
        raise EvidenceError("production canary contains audit/evidence gaps")

    candidate_failure_rate = _failure_rate(observations)
    if candidate_failure_rate > max_failure_rate:
        raise EvidenceError("production canary failure rate exceeds threshold")
    if candidate_failure_rate - stable_failure_rate > max_regression:
        raise EvidenceError("production canary failure regression exceeds threshold")
    observed_start = min(item["startedAt"] for item in observations)
    observed_end = max(item["completedAt"] for item in observations)
    observation_hours = (observed_end - observed_start).total_seconds() / 3600
    if observation_hours < minimum_hours:
        raise EvidenceError("production canary observation duration is insufficient")
    _evidence_refs(canary.get("evidenceRefs"), "canary.evidenceRefs", context["files"])

    rollback_result = _validate_rollback(bundle.get("rollback"), "rollback", context)
    rollback = _mapping(bundle.get("rollback"), "rollback")
    if rollback.get("restoredVersion") != stable_version:
        raise EvidenceError("rollback must restore the declared stable version")
    postmortem = _mapping(bundle.get("postmortem"), "postmortem")
    if postmortem.get("completed") is not True:
        raise EvidenceError("postmortem/release review must be completed")
    _text(postmortem.get("reviewedBy"), "postmortem.reviewedBy")
    _text(postmortem.get("summary"), "postmortem.summary")
    _list(postmortem.get("actionItems"), "postmortem.actionItems")
    reviewed_at = _timestamp(postmortem.get("reviewedAt"), "postmortem.reviewedAt")
    review_not_before = max(observed_end, rollback_result["completedAt"])
    if not (review_not_before <= reviewed_at <= context["expiresAt"]):
        raise EvidenceError("postmortem must follow canary and rollback inside authorization")
    _evidence_refs(postmortem.get("evidenceRefs"), "postmortem.evidenceRefs", context["files"])
    return {
        "eligiblePopulation": eligible_population,
        "selectedCount": selected_count,
        "canaryPercentage": computed_percentage,
        "sampleCount": len(observations),
        "observationHours": observation_hours,
        "candidateFailureRate": candidate_failure_rate,
        "failureRateRegression": candidate_failure_rate - stable_failure_rate,
        "safetyViolations": 0,
        "unknownCommits": 0,
        "auditGaps": 0,
        "releaseEligible": True,
    }


def validate_bundle(bundle_path: Path, expected_task_id: str | None = None) -> dict[str, Any]:
    """Validate a bundle without modifying it or manufacturing acceptance evidence."""
    bundle, context = _validate_common(bundle_path, expected_task_id)
    validators = {
        "P5-003": validate_compatibility_matrix,
        "P5-006": validate_dual_track_comparison,
        "P5-007": validate_production_canary,
    }
    result = validators[context["taskId"]](bundle, context)
    return {
        "schemaVersion": "1.0",
        "taskId": context["taskId"],
        "softwareValidation": "PASSED",
        "acceptanceEvidence": "EXTERNAL_HARDWARE_VALIDATED",
        "hardwareEvidence": True,
        "sourceBundleSha256": hashlib.sha256(bundle_path.read_bytes()).hexdigest(),
        "evidenceFiles": sorted(context["files"]),
        "evidenceFileCount": len(context["files"]),
        "result": result,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", nargs="?", type=Path)
    parser.add_argument("--task-id", choices=sorted(SUPPORTED_TASKS))
    parser.add_argument("--report", type=Path)
    parser.add_argument("--describe-contract", choices=sorted(SUPPORTED_TASKS))
    args = parser.parse_args()
    if args.describe_contract is not None:
        print(json.dumps(TASK_CONTRACTS[args.describe_contract], indent=2, ensure_ascii=False))
        return
    if args.bundle is None:
        parser.error("bundle is required unless --describe-contract is used")
    try:
        report = validate_bundle(args.bundle, args.task_id)
        if args.report is not None:
            if args.report.resolve() == args.bundle.resolve():
                raise EvidenceError("report path cannot overwrite the source bundle")
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(
                json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
        print(json.dumps(report, indent=2, ensure_ascii=False))
    except EvidenceError as exc:
        raise SystemExit(f"validation failed: {exc}") from exc


if __name__ == "__main__":
    main()
