from __future__ import annotations

import base64
from collections.abc import Callable
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

import pytest
from cloudctl_api.apk_policy import (
    canonical_analysis_payload,
    evaluate_apk_policy,
    verify_analysis_signature,
)
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

NOW = datetime(2026, 8, 31, 4, 0, tzinfo=UTC)


def signing_key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(bytes(reversed(range(32))))


def public_key_base64(private_key: Ed25519PrivateKey) -> str:
    value = private_key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    return base64.b64encode(value).decode("ascii")


def report() -> dict:
    return {
        "keyId": "apk-analyzer-1",
        "analyzer": "cloudctl-apk-analyzer",
        "analyzerVersion": "1.0.0",
        "analyzedAt": "2026-08-31T03:59:00+00:00",
        "artifactSha256": "a" * 64,
        "packageName": "com.example.target",
        "versionName": "8.32.1",
        "versionCode": 83201,
        "signatureDigest": "b" * 64,
        "minSdk": 26,
        "targetSdk": 35,
        "abis": ["arm64-v8a"],
        "permissions": ["android.permission.INTERNET"],
        "sbomSha256": "c" * 64,
        "debuggable": False,
        "usesCleartextTraffic": False,
        "verdict": "CLEAN",
        "findings": [{"ruleId": "MOB-001", "severity": "LOW", "title": "Informational"}],
    }


def expected(value: dict) -> dict:
    return {
        key: value[key]
        for key in (
            "artifactSha256",
            "packageName",
            "versionName",
            "versionCode",
            "signatureDigest",
            "minSdk",
            "targetSdk",
            "abis",
            "permissions",
            "sbomSha256",
        )
    }


def test_analysis_attestation_and_policy_accept_a_bound_clean_report() -> None:
    value = report()
    private_key = signing_key()
    signature = base64.b64encode(private_key.sign(canonical_analysis_payload(value))).decode(
        "ascii"
    )

    signature_digest = verify_analysis_signature(
        public_key_base64=public_key_base64(private_key),
        signature_base64=signature,
        report=value,
    )
    decision = evaluate_apk_policy(
        expected=expected(value),
        report=value,
        source_ref="s3://tenant/apk/com.example.target-83201.apk",
        sbom_ref="oci://registry.example/sbom/com.example.target:83201",
        now=NOW,
    )

    assert len(signature_digest) == 64
    assert decision["decision"] == "ACCEPT"
    assert decision["scanStatus"] == "CLEAN"


@pytest.mark.parametrize(
    ("mutate", "bind_after_mutation", "message"),
    [
        (lambda value: value.update({"artifactSha256": "d" * 64}), False, "artifactSha256"),
        (lambda value: value.update({"verdict": "PENDING"}), True, "not CLEAN"),
        (lambda value: value.update({"debuggable": True}), True, "debuggable"),
        (lambda value: value.update({"usesCleartextTraffic": True}), True, "cleartext"),
        (lambda value: value.update({"targetSdk": 30}), True, "targetSdk"),
        (
            lambda value: value.update(
                {"permissions": ["android.permission.REQUEST_INSTALL_PACKAGES"]}
            ),
            True,
            "denied permissions",
        ),
        (
            lambda value: value.update(
                {"findings": [{"ruleId": "MOB-999", "severity": "CRITICAL", "title": "Blocking"}]}
            ),
            True,
            "HIGH or CRITICAL",
        ),
    ],
)
def test_policy_rejects_metadata_drift_and_unsafe_analysis(
    mutate: Callable[[dict[str, Any]], None],
    bind_after_mutation: bool,
    message: str,
) -> None:
    value = report()
    submitted = expected(value)
    mutate(value)
    if bind_after_mutation:
        submitted = expected(value)
    with pytest.raises(ValueError, match=message):
        evaluate_apk_policy(
            expected=submitted,
            report=value,
            source_ref="s3://tenant/apk/app.apk",
            sbom_ref="oci://registry.example/sbom/app:1",
            now=NOW,
        )


def test_analysis_signature_rejects_tampering() -> None:
    value = report()
    private_key = signing_key()
    signature = base64.b64encode(private_key.sign(canonical_analysis_payload(value))).decode(
        "ascii"
    )
    tampered = deepcopy(value)
    tampered["permissions"].append("android.permission.CAMERA")

    with pytest.raises(ValueError, match="signature verification failed"):
        verify_analysis_signature(
            public_key_base64=public_key_base64(private_key),
            signature_base64=signature,
            report=tampered,
        )
