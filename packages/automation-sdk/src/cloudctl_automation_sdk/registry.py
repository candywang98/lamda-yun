"""Signed automation package admission and deterministic rollout gates."""

from __future__ import annotations

import base64
import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")
ROLLOUT_STAGES = (0, 5, 25, 100)


def _digest(value: str, field: str) -> str:
    if not SHA256_PATTERN.fullmatch(value):
        raise ValueError(f"{field} must be a SHA256 digest")
    return value.lower()


def canonical_json(value: dict[str, Any]) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def package_signature_payload(
    *,
    artifact_sha256: str,
    manifest: dict[str, Any],
    sbom_ref: str,
    sbom_sha256: str,
) -> bytes:
    """Bind the executable, manifest and SBOM into one signed registry statement."""
    return canonical_json(
        {
            "artifactSha256": _digest(artifact_sha256, "artifactSha256"),
            "manifest": manifest,
            "sbomRef": sbom_ref,
            "sbomSha256": _digest(sbom_sha256, "sbomSha256"),
        }
    )


def verify_package_signature(
    *, public_key_base64: str, signature_base64: str, payload: bytes
) -> str:
    """Verify an Ed25519 registry statement and return its immutable digest."""
    try:
        public_key_bytes = base64.b64decode(public_key_base64, validate=True)
        signature = base64.b64decode(signature_base64, validate=True)
        public_key = Ed25519PublicKey.from_public_bytes(public_key_bytes)
        public_key.verify(signature, payload)
    except (InvalidSignature, ValueError) as exc:
        raise ValueError("automation package signature verification failed") from exc
    return hashlib.sha256(signature).hexdigest()


@dataclass(frozen=True, slots=True)
class RolloutEvidence:
    sample_size: int
    success_count: int
    failure_count: int
    safety_violations: int
    p95_duration_ms: int

    def __post_init__(self) -> None:
        values = (
            self.sample_size,
            self.success_count,
            self.failure_count,
            self.safety_violations,
            self.p95_duration_ms,
        )
        if any(value < 0 for value in values):
            raise ValueError("rollout evidence counters cannot be negative")
        if self.success_count + self.failure_count != self.sample_size:
            raise ValueError("rollout evidence counts must equal sampleSize")

    @property
    def failure_rate(self) -> float:
        return self.failure_count / self.sample_size if self.sample_size else 0.0


def evaluate_rollout_promotion(
    *,
    current_percentage: int,
    target_percentage: int,
    evidence: RolloutEvidence,
    max_failure_rate: float = 0.02,
) -> dict[str, Any]:
    """Allow only monotonic staged promotion with measurable safety evidence."""
    if current_percentage not in ROLLOUT_STAGES or target_percentage not in ROLLOUT_STAGES:
        raise ValueError("rollout percentage must be one of 0, 5, 25 or 100")
    if current_percentage == 100:
        raise ValueError("a fully promoted rollout cannot be promoted again")
    expected_target = ROLLOUT_STAGES[ROLLOUT_STAGES.index(current_percentage) + 1]
    if target_percentage != expected_target:
        raise ValueError(f"rollout must advance from {current_percentage}% to {expected_target}%")

    minimum_samples = {5: 0, 25: 20, 100: 100}[target_percentage]
    if evidence.sample_size < minimum_samples:
        raise ValueError(
            f"promotion to {target_percentage}% requires at least {minimum_samples} samples"
        )
    if evidence.safety_violations:
        raise ValueError("rollout has safety violations and must be halted")
    if evidence.failure_rate > max_failure_rate:
        raise ValueError("rollout failure rate exceeds the promotion threshold")

    return {
        "fromPercentage": current_percentage,
        "toPercentage": target_percentage,
        "sampleSize": evidence.sample_size,
        "successCount": evidence.success_count,
        "failureCount": evidence.failure_count,
        "failureRate": evidence.failure_rate,
        "safetyViolations": evidence.safety_violations,
        "p95DurationMs": evidence.p95_duration_ms,
        "productionQualified": target_percentage == 100,
    }
