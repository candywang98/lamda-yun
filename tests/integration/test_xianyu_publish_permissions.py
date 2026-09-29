from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from cloudctl_api import create_app
from cloudctl_api.db import MobileTaskRow
from cloudctl_api.settings import Settings
from cloudctl_api.xianyu_publish import XianyuPublishQueueService
from cloudctl_domain import Actor, ForbiddenError, Role
from fastapi import FastAPI
from sqlalchemy import func, select

TENANT_A = "00000000-0000-7000-8000-000000000111"
TENANT_B = "00000000-0000-7000-8000-000000000999"
OPERATOR = "00000000-0000-7000-8000-000000000222"


def identity(*, tenant: str = TENANT_A, role: str = "device_operator") -> dict[str, str]:
    return {
        "X-Tenant-Id": tenant,
        "X-User-Id": OPERATOR,
        "X-Roles": role,
        "X-MFA": "true",
        "X-Request-Id": str(uuid.uuid4()),
    }


def actor(*roles: Role, tenant: str = TENANT_A) -> Actor:
    return Actor(
        tenant_id=uuid.UUID(tenant),
        user_id=uuid.UUID(OPERATOR),
        roles=frozenset(roles),
        mfa=True,
        request_id=str(uuid.uuid4()),
    )


@pytest.fixture
async def api() -> AsyncIterator[tuple[httpx.AsyncClient, FastAPI]]:
    app = create_app(Settings(env="test", repository_mode="memory", dev_auth_bypass=True))
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, app


async def setup_device_and_account(client: httpx.AsyncClient) -> tuple[str, str]:
    device = await client.post(
        "/api/v1/mobile/devices",
        headers=identity(),
        json={
            "logicalName": "permissions-phone",
            "androidVersion": "14",
            "companionVersion": "1.0.0",
        },
    )
    assert device.status_code == 201, device.text
    account = await client.post(
        "/api/v1/accounts",
        headers=identity(),
        json={
            "platform": "xianyu",
            "externalSubjectRef": "permissions-owner",
            "displayLabel": "permissions-owner",
            "secretRef": "vault://cloudctl/accounts/permissions-owner",
            "authorizationBasis": "Owner authorized the isolated test account.",
        },
    )
    assert account.status_code == 201, account.text
    device_id = str(device.json()["id"])
    account_id = str(account.json()["id"])
    binding = await client.post(
        f"/api/v1/accounts/{account_id}/bindings",
        headers=identity(),
        json={"deviceId": device_id, "confirmationNote": "Owner confirmed."},
    )
    assert binding.status_code == 201, binding.text
    return device_id, account_id


def queue_payload(device_id: str, account_id: str, queue_id: str) -> dict[str, Any]:
    return {
        "queueId": queue_id,
        "deviceId": device_id,
        "accountId": account_id,
        "items": [
            {
                "description": "权限隔离测试商品",
                "price": "19.90",
                "completionBoundary": "FULL_AUTO",
            }
        ],
    }


class DispatchSpy:
    def __init__(self) -> None:
        self.calls = 0

    async def create(self, *_args: Any, **_kwargs: Any) -> Any:
        self.calls += 1
        raise AssertionError("unauthorized dispatch reached the downstream task service")


async def mobile_task_count(app: FastAPI) -> int:
    async with app.state.database.unit_of_work() as session:
        return int(await session.scalar(select(func.count()).select_from(MobileTaskRow)) or 0)


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["publisher", "device_operator"])
async def test_authorized_roles_can_create_and_replay_queue(
    api: tuple[httpx.AsyncClient, FastAPI], role: str
) -> None:
    client, _ = api
    device_id, account_id = await setup_device_and_account(client)
    payload = queue_payload(device_id, account_id, f"permissions-replay-{role}")

    created = await client.post(
        "/api/v1/xianyu/publish/queues", headers=identity(role=role), json=payload
    )
    replayed = await client.post(
        "/api/v1/xianyu/publish/queues", headers=identity(role=role), json=payload
    )

    assert created.status_code == 201, created.text
    assert created.json()["replayed"] is False
    assert replayed.status_code == 201, replayed.text
    assert replayed.json()["replayed"] is True
    assert replayed.json()["targets"][0]["targetId"] == created.json()["targets"][0]["targetId"]


@pytest.mark.asyncio
async def test_http_denied_mutations_leave_queue_and_tasks_unchanged(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = api
    device_id, account_id = await setup_device_and_account(client)
    publisher = identity(role="publisher")
    payload = queue_payload(device_id, account_id, "permissions-denied")
    created = await client.post("/api/v1/xianyu/publish/queues", headers=publisher, json=payload)
    assert created.status_code == 201, created.text
    target_id = created.json()["targets"][0]["targetId"]
    before = (
        await client.get("/api/v1/xianyu/publish/queues/permissions-denied", headers=publisher)
    ).json()
    spy = DispatchSpy()
    app.state.platform_task_service = spy

    for role in ("viewer", "content_editor"):
        headers = identity(role=role)
        denied_create = await client.post(
            "/api/v1/xianyu/publish/queues",
            headers=headers,
            json=queue_payload(device_id, account_id, f"permissions-create-{role}"),
        )
        denied_next = await client.post(
            "/api/v1/xianyu/publish/queues/permissions-denied/next", headers=headers
        )
        denied_dispatch = await client.post(
            f"/api/v1/xianyu/publish/queues/permissions-denied/targets/{target_id}/dispatch",
            headers=headers,
        )
        denied_failure = await client.post(
            f"/api/v1/xianyu/publish/queues/permissions-denied/targets/{target_id}/report-failure",
            headers=headers,
            json={"errorCode": "TEST_FAILURE", "detail": "must not be recorded"},
        )
        denied_confirm = await client.post(
            f"/api/v1/xianyu/publish/queues/permissions-denied/targets/{target_id}/confirm",
            headers=headers,
            json={"decision": "FAILED", "evidence": {}, "operatorNote": "must not persist"},
        )

        assert denied_create.status_code == 403, denied_create.text
        assert denied_next.status_code == 403, denied_next.text
        assert denied_dispatch.status_code == 403, denied_dispatch.text
        assert denied_failure.status_code == 403, denied_failure.text
        assert denied_confirm.status_code == 403, denied_confirm.text

    after = (
        await client.get("/api/v1/xianyu/publish/queues/permissions-denied", headers=publisher)
    ).json()
    assert after == before
    target = after["targets"][0]
    assert target["state"] == "PENDING"
    assert target["taskIds"] == []
    assert target["confirmedAt"] is None
    assert target["result"] == {}
    assert spy.calls == 0
    assert await mobile_task_count(app) == 0

    for role in ("viewer", "content_editor"):
        missing = await client.get(
            f"/api/v1/xianyu/publish/queues/permissions-create-{role}", headers=publisher
        )
        assert missing.status_code == 404


@pytest.mark.asyncio
async def test_http_read_authentication_and_tenant_boundaries(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = api
    device_id, account_id = await setup_device_and_account(client)
    payload = queue_payload(device_id, account_id, "permissions-read")
    created = await client.post(
        "/api/v1/xianyu/publish/queues", headers=identity(role="publisher"), json=payload
    )
    assert created.status_code == 201, created.text
    target_id = created.json()["targets"][0]["targetId"]
    spy = DispatchSpy()
    app.state.platform_task_service = spy

    viewer_read = await client.get(
        "/api/v1/xianyu/publish/queues/permissions-read", headers=identity(role="viewer")
    )
    no_read = await client.get(
        "/api/v1/xianyu/publish/queues/permissions-read",
        headers=identity(role="content_editor"),
    )
    missing_read = await client.get("/api/v1/xianyu/publish/queues/permissions-read")
    missing_create = await client.post("/api/v1/xianyu/publish/queues", json=payload)
    cross_read = await client.get(
        "/api/v1/xianyu/publish/queues/permissions-read",
        headers=identity(tenant=TENANT_B, role="viewer"),
    )
    cross_next = await client.post(
        "/api/v1/xianyu/publish/queues/permissions-read/next",
        headers=identity(tenant=TENANT_B, role="publisher"),
    )
    cross_dispatch = await client.post(
        f"/api/v1/xianyu/publish/queues/permissions-read/targets/{target_id}/dispatch",
        headers=identity(tenant=TENANT_B, role="device_operator"),
    )

    assert viewer_read.status_code == 200, viewer_read.text
    assert viewer_read.json()["queueId"] == "permissions-read"
    assert no_read.status_code == 403, no_read.text
    assert missing_read.status_code == 401, missing_read.text
    assert missing_create.status_code == 401, missing_create.text
    assert cross_read.status_code == 404, cross_read.text
    assert cross_next.status_code == 404, cross_next.text
    assert cross_dispatch.status_code == 404, cross_dispatch.text
    assert spy.calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("role", [Role.VIEWER, Role.CONTENT_EDITOR])
async def test_service_permissions_precede_payload_lookup_state_and_dispatch(
    api: tuple[httpx.AsyncClient, FastAPI], role: Role
) -> None:
    _, app = api
    service = XianyuPublishQueueService(app.state.database)
    spy = DispatchSpy()
    denied = actor(role)

    with pytest.raises(ForbiddenError, match="task.create"):
        await service.create_queue(denied, {})
    with pytest.raises(ForbiddenError, match="task.create"):
        await service.next_target(denied, "missing-queue")
    with pytest.raises(ForbiddenError, match="task.create"):
        await service.dispatch(denied, "missing-queue", "missing-target", spy)
    with pytest.raises(ForbiddenError, match="task.create"):
        await service.report_failure(denied, "missing-queue", "missing-target", {})
    with pytest.raises(ForbiddenError, match="task.create"):
        await service.confirm(denied, "missing-queue", "missing-target", {})

    with pytest.raises(ForbiddenError, match="publish.read"):
        await service.get_queue(actor(), "missing-queue")
    assert spy.calls == 0


@pytest.mark.asyncio
async def test_http_authorization_precedes_missing_target_errors_and_dispatch(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = api
    spy = DispatchSpy()
    app.state.platform_task_service = spy
    missing_dispatch = "/api/v1/xianyu/publish/queues/missing/targets/missing/dispatch"

    denied_next = await client.post(
        "/api/v1/xianyu/publish/queues/missing/next", headers=identity(role="viewer")
    )
    denied_dispatch = await client.post(missing_dispatch, headers=identity(role="viewer"))
    authorized_next = await client.post(
        "/api/v1/xianyu/publish/queues/missing/next", headers=identity(role="publisher")
    )
    authorized_dispatch = await client.post(missing_dispatch, headers=identity(role="publisher"))

    assert denied_next.status_code == 403, denied_next.text
    assert denied_dispatch.status_code == 403, denied_dispatch.text
    assert authorized_next.status_code == 404, authorized_next.text
    assert authorized_dispatch.status_code == 404, authorized_dispatch.text
    assert spy.calls == 0
