from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import httpx
import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "export-audit.py"
TENANT = "00000000-0000-7000-8000-00000000e001"


def load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("export_audit", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_fetch_and_write_export_redacts_secrets_and_uses_environment_token(
    tmp_path: Path,
) -> None:
    module = load_module()

    def respond(request: httpx.Request) -> httpx.Response:
        assert request.url.params["limit"] == "25"
        assert request.headers["Authorization"] == "Bearer environment-only-token"
        return httpx.Response(
            200,
            json=[
                {
                    "id": "audit-1",
                    "tenant_id": TENANT,
                    "action": "debug.session.created",
                    "metadata_json": {
                        "relay_token": "raw-secret",
                        "accessToken": "camel-case-secret",
                        "fencing_token": 7,
                    },
                }
            ],
        )

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        origin, events = module.fetch_events(
            "https://api.example.test",
            "environment-only-token",
            25,
            client=client,
        )
    output = tmp_path / "audit.json"
    result = module.write_export(origin, events, output)
    document = json.loads(output.read_text(encoding="utf-8"))

    assert result["eventCount"] == 1
    assert document["tenantId"] == TENANT
    assert document["events"][0]["metadata_json"]["relay_token"] == "[REDACTED]"  # noqa: S105
    assert document["events"][0]["metadata_json"]["accessToken"] == "[REDACTED]"  # noqa: S105
    assert document["events"][0]["metadata_json"]["fencing_token"] == 7
    assert "raw-secret" not in output.read_text(encoding="utf-8")
    assert "camel-case-secret" not in output.read_text(encoding="utf-8")
    assert output.stat().st_mode & 0o777 == 0o600
    checksum = output.with_name("audit.json.sha256").read_text(encoding="utf-8")
    assert checksum == f"{result['sha256']}  audit.json\n"


def test_export_rejects_cross_tenant_payloads() -> None:
    module = load_module()
    events = [
        {"tenant_id": TENANT, "id": "one"},
        {"tenant_id": "00000000-0000-7000-8000-00000000e999", "id": "two"},
    ]

    with pytest.raises(module.AuditExportError, match="multiple tenants"):
        module.normalize_events(events)


@pytest.mark.parametrize(
    "url",
    [
        "http://api.example.test",
        "https://user:password@api.example.test",
        "https://api.example.test?token=secret",
    ],
)
def test_export_rejects_unsafe_origins(url: str) -> None:
    module = load_module()

    with pytest.raises(module.AuditExportError):
        module.validate_base_url(url)


def test_loopback_http_requires_explicit_test_override() -> None:
    module = load_module()

    with pytest.raises(module.AuditExportError):
        module.validate_base_url("http://127.0.0.1:8000")
    assert (
        module.validate_base_url("http://127.0.0.1:8000", allow_loopback_http=True)
        == "http://127.0.0.1:8000"
    )
