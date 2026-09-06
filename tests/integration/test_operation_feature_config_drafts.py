from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from cloudctl_api import create_app
from cloudctl_api.settings import Settings
from pydantic import SecretStr

TENANT = "00000000-0000-7000-8000-000000001111"
OTHER_TENANT = "00000000-0000-7000-8000-000000009999"
USER = "00000000-0000-7000-8000-000000002222"


def headers(
    roles: str,
    *,
    tenant_id: str = TENANT,
    user_id: str = USER,
    idempotency_key: str | None = None,
) -> dict[str, str]:
    values = {
        "X-Tenant-Id": tenant_id,
        "X-User-Id": user_id,
        "X-Roles": roles,
        "X-MFA": "true",
        "X-Request-Id": str(uuid.uuid4()),
    }
    if idempotency_key is not None:
        values["Idempotency-Key"] = idempotency_key
    return values


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(
        Settings(
            env="test",
            repository_mode="memory",
            dev_auth_bypass=True,
            operation_executor_urls={
                "media.derivative.generate": "https://executor.test/media-derivative",
                "watermarks.preview.render": "https://executor.test/watermark-preview",
            },
            operation_executor_bearer_token=SecretStr("test-operation-token"),
        )
    )
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as value:
            yield value


@pytest.mark.asyncio
async def test_config_draft_lifecycle_tenant_isolation_rbac_and_audit(
    client: httpx.AsyncClient,
) -> None:
    path = "/api/v1/operations/features/assets-01/config-draft"
    empty = await client.get(path, headers=headers("viewer"))
    assert empty.status_code == 200
    assert empty.json() == {
        "featureId": "assets-01",
        "configuration": {},
        "version": 0,
        "exists": False,
        "createdAt": None,
        "updatedAt": None,
        "updatedBy": None,
    }

    forbidden = await client.put(
        path,
        headers=headers("viewer"),
        json={"configuration": {"opacity": 0.5}, "expectedVersion": 0},
    )
    assert forbidden.status_code == 403

    first = await client.put(
        path,
        headers=headers("automation_developer"),
        json={
            "configuration": {
                "opacity": 0.55,
                "preset": {"name": "brand", "positions": ["top-left"]},
                "description": "tenant draft only",
            },
            "expectedVersion": 0,
        },
    )
    assert first.status_code == 200, first.text
    assert first.json()["version"] == 1
    assert first.json()["exists"] is True
    assert first.json()["updatedBy"] == USER

    stale = await client.put(
        path,
        headers=headers("automation_developer"),
        json={"configuration": {"opacity": 0.6}, "expectedVersion": 0},
    )
    assert stale.status_code == 409

    second = await client.put(
        path,
        headers=headers("security_admin"),
        json={"configuration": {"opacity": 0.6}, "expectedVersion": 1},
    )
    assert second.status_code == 200, second.text
    assert second.json()["version"] == 2

    other_tenant_empty = await client.get(
        path,
        headers=headers("viewer", tenant_id=OTHER_TENANT),
    )
    assert other_tenant_empty.status_code == 200
    assert other_tenant_empty.json()["exists"] is False
    assert other_tenant_empty.json()["version"] == 0

    other_tenant_write = await client.put(
        path,
        headers=headers("automation_developer", tenant_id=OTHER_TENANT),
        json={"configuration": {"opacity": 0.2}, "expectedVersion": 0},
    )
    assert other_tenant_write.status_code == 200
    assert other_tenant_write.json()["version"] == 1
    original = await client.get(path, headers=headers("viewer"))
    assert original.json()["configuration"] == {"opacity": 0.6}
    assert original.json()["version"] == 2

    audit = await client.get("/api/v1/audit-events?limit=20", headers=headers("security_admin"))
    assert audit.status_code == 200
    events = [
        event
        for event in audit.json()
        if event["resource_type"] == "operation_feature_config_draft"
        and event["resource_id"] == "assets-01"
    ]
    assert {event["action"] for event in events} == {
        "operation.feature_config_draft.created",
        "operation.feature_config_draft.updated",
    }
    assert all(event["after_hash"] for event in events)
    updated = next(
        event for event in events if event["action"] == "operation.feature_config_draft.updated"
    )
    assert updated["before_hash"] is not None
    assert updated["metadata_json"] == {
        "featureId": "assets-01",
        "featurePolicy": "mapped",
        "featureExecutionState": "implemented",
    }


@pytest.mark.asyncio
async def test_all_134_features_are_draftable_without_changing_execution_policy(
    client: httpx.AsyncClient,
) -> None:
    before_response = await client.get(
        "/api/v1/operations/features",
        headers=headers("automation_developer"),
    )
    assert before_response.status_code == 200
    before = before_response.json()
    assert len(before) == 134

    for feature in before:
        response = await client.put(
            f"/api/v1/operations/features/{feature['featureId']}/config-draft",
            headers=headers("automation_developer"),
            json={
                "configuration": {
                    "uiDraft": {"label": feature["title"], "visibleColumns": ["name"]}
                },
                "expectedVersion": 0,
            },
        )
        assert response.status_code == 200, (feature["featureId"], response.text)
        assert response.json()["version"] == 1

    after = (
        await client.get(
            "/api/v1/operations/features",
            headers=headers("automation_developer"),
        )
    ).json()
    assert after == before
    blocked = next(feature for feature in after if feature["featureId"] == "collection-01")
    ui_only = next(feature for feature in after if feature["featureId"] == "system-home-01")
    assert (blocked["executionState"], blocked["executable"]) == ("blocked", False)
    assert (ui_only["executionState"], ui_only["executable"]) == ("ui_only", False)

    blocked_task = await client.post(
        "/api/v1/operations/tasks",
        headers=headers("security_admin", idempotency_key="configured-blocked-feature"),
        json={
            "featureId": "collection-01",
            "operationKey": "media.derivative.generate",
            "resourceId": "external-link",
        },
    )
    assert blocked_task.status_code == 403
    ui_only_task = await client.post(
        "/api/v1/operations/tasks",
        headers=headers("security_admin", idempotency_key="configured-ui-only-feature"),
        json={
            "featureId": "system-home-01",
            "operationKey": "media.derivative.generate",
            "resourceId": "dashboard",
        },
    )
    assert ui_only_task.status_code == 403


@pytest.mark.asyncio
async def test_config_draft_api_rejects_unknown_features_and_unsafe_json(
    client: httpx.AsyncClient,
) -> None:
    unknown_path = "/api/v1/operations/features/not-in-catalog/config-draft"
    assert (await client.get(unknown_path, headers=headers("viewer"))).status_code == 404
    unknown_put = await client.put(
        unknown_path,
        headers=headers("automation_developer"),
        json={"configuration": {}, "expectedVersion": 0},
    )
    assert unknown_put.status_code == 404

    path = "/api/v1/operations/features/assets-01/config-draft"
    for dangerous_key in (
        "executionState",
        "operation-key",
        "accessToken",
        "__proto__",
        "shellCommand",
        "$where",
    ):
        response = await client.put(
            path,
            headers=headers("automation_developer"),
            json={"configuration": {dangerous_key: "value"}, "expectedVersion": 0},
        )
        assert response.status_code == 422, (dangerous_key, response.text)

    nested: dict[str, object] = {}
    cursor = nested
    for index in range(8):
        child: dict[str, object] = {}
        cursor[f"level{index}"] = child
        cursor = child
    too_deep = await client.put(
        path,
        headers=headers("automation_developer"),
        json={"configuration": nested, "expectedVersion": 0},
    )
    assert too_deep.status_code == 422

    too_large = await client.put(
        path,
        headers=headers("automation_developer"),
        json={
            "configuration": {f"section{index}": "x" * 8_000 for index in range(9)},
            "expectedVersion": 0,
        },
    )
    assert too_large.status_code == 422
    assert (await client.get(path, headers=headers("viewer"))).json()["exists"] is False
