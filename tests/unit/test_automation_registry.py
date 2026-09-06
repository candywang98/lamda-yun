from __future__ import annotations

import base64

import pytest
from cloudctl_automation_sdk import (
    RolloutEvidence,
    evaluate_rollout_promotion,
    package_signature_payload,
    verify_package_signature,
)
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def signing_key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(bytes(range(32)))


def public_key_base64(private_key: Ed25519PrivateKey) -> str:
    value = private_key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    return base64.b64encode(value).decode("ascii")


def package_payload() -> bytes:
    return package_signature_payload(
        artifact_sha256="a" * 64,
        manifest={"kind": "AutomationPackage", "metadata": {"version": "1.0.0"}},
        sbom_ref="oci://registry.example/cloudctl/publisher-sbom:1.0.0",
        sbom_sha256="b" * 64,
    )


def test_signed_package_statement_binds_artifact_manifest_and_sbom() -> None:
    private_key = signing_key()
    signature = base64.b64encode(private_key.sign(package_payload())).decode("ascii")

    digest = verify_package_signature(
        public_key_base64=public_key_base64(private_key),
        signature_base64=signature,
        payload=package_payload(),
    )

    assert len(digest) == 64
    with pytest.raises(ValueError, match="signature verification failed"):
        verify_package_signature(
            public_key_base64=public_key_base64(private_key),
            signature_base64=signature,
            payload=package_payload() + b"tampered",
        )


def test_rollout_requires_staged_promotion_and_measured_health() -> None:
    canary = evaluate_rollout_promotion(
        current_percentage=0,
        target_percentage=5,
        evidence=RolloutEvidence(0, 0, 0, 0, 0),
    )
    assert canary["productionQualified"] is False

    expanded = evaluate_rollout_promotion(
        current_percentage=5,
        target_percentage=25,
        evidence=RolloutEvidence(20, 20, 0, 0, 1300),
    )
    assert expanded["toPercentage"] == 25

    qualified = evaluate_rollout_promotion(
        current_percentage=25,
        target_percentage=100,
        evidence=RolloutEvidence(100, 99, 1, 0, 1500),
    )
    assert qualified["productionQualified"] is True


@pytest.mark.parametrize(
    ("current", "target", "evidence", "message"),
    [
        (0, 25, RolloutEvidence(20, 20, 0, 0, 1000), "advance from 0% to 5%"),
        (5, 25, RolloutEvidence(19, 19, 0, 0, 1000), "at least 20 samples"),
        (5, 25, RolloutEvidence(20, 19, 1, 1, 1000), "safety violations"),
        (25, 100, RolloutEvidence(100, 97, 3, 0, 1000), "failure rate"),
    ],
)
def test_rollout_rejects_skips_weak_samples_and_unhealthy_results(
    current: int,
    target: int,
    evidence: RolloutEvidence,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        evaluate_rollout_promotion(
            current_percentage=current,
            target_percentage=target,
            evidence=evidence,
        )
