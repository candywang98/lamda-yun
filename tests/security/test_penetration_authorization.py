from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from cloudctl_api import create_app
from cloudctl_api.settings import Settings

TENANT_A = "00000000-0000-7000-8000-00000000d001"
TENANT_B = "00000000-0000-7000-8000-00000000d002"
USER_A = "00000000-0000-7000-8000-00000000d101"


def headers(
    role: str,
    *,
    tenant_id: str = TENANT_A,
    user_id: str = USER_A,
    idempotency_key: str | None = None,
) -> dict[str, str]:
    value = {
        "X-Tenant-Id": tenant_id,
        "X-User-Id": user_id,
        "X-Roles": role,
        "X-MFA": "true",
        "X-Request-Id": str(uuid.uuid4()),
    }
    if idempotency_key is not None:
        value["Idempotency-Key"] = idempotency_key
    return value


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(Settings(env="test", repository_mode="memory", dev_auth_bypass=True))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://security.test"
        ) as value:
            yield value


@pytest.mark.asyncio
async def test_protected_routes_fail_closed_and_do_not_honor_viewer_escalation(
    client: httpx.AsyncClient,
) -> None:
    unauthenticated = await client.get("/api/v1/audit-events")
    viewer = await client.get("/api/v1/audit-events", headers=headers("viewer"))
    security_admin = await client.get("/api/v1/audit-events", headers=headers("security_admin"))

    assert unauthenticated.status_code == 401
    assert unauthenticated.json()["code"] == "AUTHENTICATION_REQUIRED"
    assert viewer.status_code == 403
    assert viewer.json()["code"] == "FORBIDDEN"
    assert security_admin.status_code == 200


@pytest.mark.asyncio
async def test_cross_tenant_object_lookup_is_indistinguishable_from_missing(
    client: httpx.AsyncClient,
) -> None:
    created = await client.post(
        "/api/v1/operations/tasks",
        headers=headers("content_editor", idempotency_key="security-tenant-probe"),
        json={
            "operationKey": "works.revision.validate",
            "resourceId": "revision-security-probe",
            "parameters": {"policyVersion": "security-baseline"},
        },
    )
    assert created.status_code == 201, created.text
    task_id = str(created.json()["id"])

    hidden = await client.get(
        f"/api/v1/operations/tasks/{task_id}",
        headers=headers("content_editor", tenant_id=TENANT_B),
    )
    missing = await client.get(
        f"/api/v1/operations/tasks/{uuid.uuid4()}",
        headers=headers("content_editor", tenant_id=TENANT_B),
    )

    assert hidden.status_code == 404
    assert missing.status_code == 404
    assert hidden.json()["code"] == missing.json()["code"]
    assert task_id not in hidden.text


@pytest.mark.asyncio
async def test_untrusted_evidence_references_and_human_result_spoofing_are_denied(
    client: httpx.AsyncClient,
) -> None:
    created = await client.post(
        "/api/v1/operations/tasks",
        headers=headers("content_editor", idempotency_key="security-result-probe"),
        json={
            "operationKey": "works.revision.validate",
            "resourceId": "revision-result-probe",
        },
    )
    assert created.status_code == 201, created.text
    task_id = str(created.json()["id"])
    endpoint = f"/api/v1/operations/tasks/{task_id}/items/revision-result-probe:result"

    human = await client.post(
        endpoint,
        headers=headers("security_admin"),
        json={"status": "SUCCEEDED", "evidenceRefs": ["s3://tenant/valid.json"]},
    )
    service_with_local_path = await client.post(
        endpoint,
        headers=headers("system_service"),
        json={"status": "SUCCEEDED", "evidenceRefs": ["file:///tmp/stolen.json"]},
    )

    assert human.status_code == 403
    assert service_with_local_path.status_code == 422


@pytest.mark.asyncio
async def test_problem_details_preserve_correlation_without_secret_echo(
    client: httpx.AsyncClient,
) -> None:
    request_id = "security-correlation-probe"
    response = await client.get(
        "/api/v1/audit-events",
        headers={
            **headers("viewer"),
            "Authorization": "Bearer should-never-be-echoed",
            "X-Request-Id": request_id,
        },
    )

    assert response.status_code == 403
    assert response.headers["X-Request-Id"] == request_id
    assert response.json()["correlation_id"] == request_id
    assert "should-never-be-echoed" not in response.text
