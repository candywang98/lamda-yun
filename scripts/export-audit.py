#!/usr/bin/env python3
"""Export a tenant-scoped, redacted CloudCtl audit bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

MAX_RESPONSE_BYTES = 10 * 1024 * 1024
SENSITIVE_KEYS = {
    "access_token",
    "authorization",
    "binding_token",
    "client_secret",
    "cookie",
    "credential",
    "credentials",
    "launch_code",
    "oidc_public_key_pem",
    "password",
    "pem",
    "private_key",
    "refresh_token",
    "relay_token",
    "secret",
    "set-cookie",
    "token",
}
NORMALIZED_SENSITIVE_KEYS = {
    "".join(character for character in key.casefold() if character.isalnum())
    for key in SENSITIVE_KEYS
}
SENSITIVE_VALUE_MARKERS = (
    "-----BEGIN " + "CERTIFICATE-----",
    "-----BEGIN " + "PRIVATE KEY-----",
    "-----BEGIN RSA " + "PRIVATE KEY-----",
    "-----BEGIN OPENSSH " + "PRIVATE KEY-----",
)


class AuditExportError(RuntimeError):
    """Raised when an audit export is unsafe or invalid."""


def validate_base_url(base_url: str, *, allow_loopback_http: bool = False) -> str:
    parsed = urlsplit(base_url.rstrip("/"))
    if parsed.username is not None or parsed.password is not None:
        raise AuditExportError("audit export URL must not contain credentials")
    if parsed.query or parsed.fragment or not parsed.netloc:
        raise AuditExportError("audit export URL must be an origin without query or fragment")
    loopback = parsed.hostname in {"127.0.0.1", "::1", "localhost"}
    if parsed.scheme != "https" and not (
        parsed.scheme == "http" and loopback and allow_loopback_http
    ):
        raise AuditExportError("audit export requires HTTPS except explicit loopback testing")
    return f"{parsed.scheme}://{parsed.netloc}"


def _redact(value: Any, key: str | None = None) -> Any:
    normalized_key = (
        "".join(character for character in key.casefold() if character.isalnum())
        if key is not None
        else None
    )
    if normalized_key is not None and normalized_key in NORMALIZED_SENSITIVE_KEYS:
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(item_key): _redact(item, str(item_key)) for item_key, item in value.items()}
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, str) and any(marker in value for marker in SENSITIVE_VALUE_MARKERS):
        return "[REDACTED]"
    return value


def normalize_events(payload: Any) -> tuple[str | None, list[dict[str, Any]]]:
    if not isinstance(payload, list):
        raise AuditExportError("audit endpoint response must be a JSON array")
    events: list[dict[str, Any]] = []
    tenants: set[str] = set()
    for index, raw_event in enumerate(payload):
        if not isinstance(raw_event, dict):
            raise AuditExportError(f"audit event {index} is not an object")
        event = _redact(raw_event)
        assert isinstance(event, dict)
        tenant = event.get("tenant_id", event.get("tenantId"))
        if tenant is not None:
            tenants.add(str(tenant))
        events.append(event)
    if len(tenants) > 1:
        raise AuditExportError("audit export contains events from multiple tenants")
    return (next(iter(tenants)) if tenants else None), events


def fetch_events(
    base_url: str,
    token: str,
    limit: int,
    *,
    allow_loopback_http: bool = False,
    client: httpx.Client | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    if not token or len(token.encode("utf-8")) > 16_384:
        raise AuditExportError("audit bearer token is missing or oversized")
    if limit < 1 or limit > 500:
        raise AuditExportError("audit limit must be between 1 and 500")
    origin = validate_base_url(base_url, allow_loopback_http=allow_loopback_http)
    owns_client = client is None
    active_client = client or httpx.Client(
        timeout=15.0,
        follow_redirects=False,
        trust_env=False,
    )
    try:
        response = active_client.get(
            f"{origin}/api/v1/audit-events",
            params={"limit": limit},
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {token}",
                "X-Request-Id": f"audit-export-{os.getpid()}",
            },
        )
        if len(response.content) > MAX_RESPONSE_BYTES:
            raise AuditExportError("audit response exceeds 10 MiB")
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            raise AuditExportError(
                f"audit endpoint returned HTTP {response.status_code}"
            ) from error
        try:
            payload = response.json()
        except ValueError as error:
            raise AuditExportError("audit endpoint did not return valid JSON") from error
    finally:
        if owns_client:
            active_client.close()
    _, events = normalize_events(payload)
    return origin, events


def _atomic_private_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.next")
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        path.chmod(0o600)
    finally:
        temporary.unlink(missing_ok=True)


def write_export(origin: str, events: list[dict[str, Any]], output: Path) -> dict[str, Any]:
    tenant_id, normalized = normalize_events(events)
    document = {
        "eventCount": len(normalized),
        "events": normalized,
        "exportedAt": datetime.now(UTC).isoformat(),
        "schemaVersion": 1,
        "sourceOrigin": origin,
        "tenantId": tenant_id,
    }
    encoded = (json.dumps(document, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode()
    digest = hashlib.sha256(encoded).hexdigest()
    _atomic_private_write(output, encoded)
    _atomic_private_write(
        output.with_name(f"{output.name}.sha256"),
        f"{digest}  {output.name}\n".encode(),
    )
    return {"bytes": len(encoded), "eventCount": len(normalized), "sha256": digest}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--token-env", default="CLOUDCTL_AUDIT_EXPORT_TOKEN")
    parser.add_argument("--allow-loopback-http", action="store_true")
    args = parser.parse_args()

    token = os.environ.get(args.token_env, "")
    origin, events = fetch_events(
        args.base_url,
        token,
        args.limit,
        allow_loopback_http=args.allow_loopback_http,
    )
    result = write_export(origin, events, args.output.resolve())
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
