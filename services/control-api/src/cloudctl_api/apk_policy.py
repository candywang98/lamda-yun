"""Signed APK analysis attestation and admission policy."""

from __future__ import annotations

import base64
import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")
ALLOWED_REFERENCE_SCHEMES = frozenset({"https", "oci", "s3"})
ALLOWED_ABIS = frozenset({"arm64-v8a", "armeabi-v7a", "x86", "x86_64"})
BLOCKING_SEVERITIES = frozenset({"HIGH", "CRITICAL"})
DEFAULT_DENIED_PERMISSIONS = frozenset(
    {
        "android.permission.BIND_DEVICE_ADMIN",
        "android.permission.MANAGE_DEVICE_ADMINS",
        "android.permission.REQUEST_DELETE_PACKAGES",
        "android.permission.REQUEST_INSTALL_PACKAGES",
    }
)


def canonical_analysis_payload(report: dict[str, Any]) -> bytes:
    return json.dumps(
        report,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def verify_analysis_signature(
    *, public_key_base64: str, signature_base64: str, report: dict[str, Any]
) -> str:
    try:
        public_key_bytes = base64.b64decode(public_key_base64, validate=True)
        signature = base64.b64decode(signature_base64, validate=True)
        public_key = Ed25519PublicKey.from_public_bytes(public_key_bytes)
        public_key.verify(signature, canonical_analysis_payload(report))
    except (InvalidSignature, ValueError) as exc:
        raise ValueError("APK analysis signature verification failed") from exc
    return hashlib.sha256(signature).hexdigest()


def _validate_reference(value: str, field: str) -> None:
    parsed = urlsplit(value)
    if parsed.scheme not in ALLOWED_REFERENCE_SCHEMES or not parsed.netloc:
        raise ValueError(f"{field} must be an HTTPS, OCI or S3 reference")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError(f"{field} cannot contain credentials")
    if parsed.query or parsed.fragment:
        raise ValueError(f"{field} cannot contain query or fragment")


def evaluate_apk_policy(
    *,
    expected: dict[str, Any],
    report: dict[str, Any],
    source_ref: str,
    sbom_ref: str,
    now: datetime,
    denied_permissions: frozenset[str] = DEFAULT_DENIED_PERMISSIONS,
) -> dict[str, Any]:
    """Validate a signed analyzer report against submitted metadata and policy."""
    _validate_reference(source_ref, "sourceRef")
    _validate_reference(sbom_ref, "sbomRef")

    for field, value in expected.items():
        if report.get(field) != value:
            raise ValueError(f"analysis report does not match submitted {field}")

    analyzed_at = datetime.fromisoformat(str(report["analyzedAt"]).replace("Z", "+00:00"))
    if analyzed_at.tzinfo is None:
        analyzed_at = analyzed_at.replace(tzinfo=UTC)
    current = now if now.tzinfo is not None else now.replace(tzinfo=UTC)
    if analyzed_at > current + timedelta(minutes=5):
        raise ValueError("analysis report timestamp is in the future")
    if analyzed_at < current - timedelta(days=7):
        raise ValueError("analysis report is older than seven days")

    if report.get("verdict") != "CLEAN":
        raise ValueError("APK analyzer verdict is not CLEAN")
    if report.get("debuggable") is not False:
        raise ValueError("debuggable APKs are not eligible for admission")
    if report.get("usesCleartextTraffic") is not False:
        raise ValueError("APK allows cleartext traffic")
    if int(report["targetSdk"]) < 31:
        raise ValueError("APK targetSdk is below the admission baseline")
    if int(report["minSdk"]) > int(report["targetSdk"]):
        raise ValueError("APK minSdk cannot exceed targetSdk")

    abis = set(report["abis"])
    if not abis or not abis.issubset(ALLOWED_ABIS):
        raise ValueError("APK contains an unsupported or empty ABI set")
    denied = sorted(set(report["permissions"]) & denied_permissions)
    if denied:
        raise ValueError(f"APK requests denied permissions: {denied}")

    blocking_findings = [
        finding for finding in report["findings"] if finding.get("severity") in BLOCKING_SEVERITIES
    ]
    if blocking_findings:
        raise ValueError("APK analysis contains HIGH or CRITICAL findings")

    return {
        "decision": "ACCEPT",
        "scanStatus": "CLEAN",
        "analyzer": report["analyzer"],
        "analyzerVersion": report["analyzerVersion"],
        "analysisKeyId": report["keyId"],
        "analyzedAt": report["analyzedAt"],
        "evaluatedAt": current.isoformat(),
        "findingCount": len(report["findings"]),
        "deniedPermissionCount": 0,
    }
