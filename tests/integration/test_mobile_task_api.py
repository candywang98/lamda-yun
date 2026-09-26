from __future__ import annotations

import base64
import copy
import hashlib
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from cloudctl_api import create_app
from cloudctl_api.db import MobileEnrollmentRow, MobileTaskRow, PlatformAccountRow
from cloudctl_api.settings import Settings
from cloudctl_api.xianyu_publish import XIANYU_PACKAGE, build_text_publish_task
from fastapi import FastAPI

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


@pytest.fixture
async def api() -> AsyncIterator[tuple[httpx.AsyncClient, FastAPI]]:
    app = create_app(Settings(env="test", repository_mode="memory", dev_auth_bypass=True))
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, app


async def create_device(client: httpx.AsyncClient, *, tenant: str = TENANT_A) -> str:
    headers = identity(tenant=tenant, role="security_admin")
    edge = await client.post(
        "/api/v1/edges",
        headers=headers,
        json={
            "logicalName": f"edge-{tenant[-4:]}",
            "certificateFingerprint": "ab" * 32,
        },
    )
    assert edge.status_code == 201, edge.text
    device = await client.post(
        "/api/v1/devices",
        headers=headers,
        json={
            "edgeId": edge.json()["id"],
            "logicalName": f"device-{tenant[-4:]}",
            "androidVersion": "14",
            "lamdaVersion": "10.8",
            "labels": ["mobile-direct"],
        },
    )
    assert device.status_code == 201, device.text
    return str(device.json()["id"])


async def create_direct_device(client: httpx.AsyncClient) -> str:
    response = await client.post(
        "/api/v1/mobile/devices",
        headers=identity(),
        json={
            "logicalName": "oneplus-9r-direct",
            "androidVersion": "14",
            "companionVersion": "1.0.0",
            "labels": ["mobile-direct"],
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["edgeId"] is None
    assert response.json()["capabilities"]["mobileDirect"] is True
    return str(response.json()["id"])


def task_body(device_id: str) -> dict[str, Any]:
    return {
        "deviceId": device_id,
        "targetPackage": "com.company.cloudctl.companion",
        "totalTimeoutMs": 30_000,
        "steps": [
            {
                "stepId": "find-submit",
                "action": "ui.find",
                "locatorRef": "screen.submit",
                "timeoutMs": 5_000,
            },
            {
                "stepId": "tap-submit",
                "action": "ui.tap",
                "locatorRef": "screen.submit",
                "postconditionLocatorRef": "screen.confirmation",
                "timeoutMs": 5_000,
            },
        ],
    }


async def enroll(
    client: httpx.AsyncClient, device_id: str, *, instance: str = "instance-0001"
) -> str:
    created = await client.post(
        "/api/v1/mobile/enrollments",
        headers=identity(),
        json={"deviceId": device_id, "ttlSeconds": 600},
    )
    assert created.status_code == 201, created.text
    response = await client.post(
        "/companion/v2/enroll",
        json={
            "code": created.json()["code"],
            "appInstanceId": instance,
            "companionVersion": "1.0.0",
        },
    )
    assert response.status_code == 201, response.text
    return str(response.json()["bindingToken"])


async def create_account(
    client: httpx.AsyncClient,
    *,
    platform: str,
    subject: str,
    label: str,
) -> str:
    response = await client.post(
        "/api/v1/accounts",
        headers=identity(),
        json={
            "platform": platform,
            "externalSubjectRef": subject,
            "displayLabel": label,
            "secretRef": f"vault://cloudctl/accounts/{subject}",
            "authorizationBasis": "Owner authorized the test account.",
        },
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


async def bind_account(
    client: httpx.AsyncClient, account_id: str, device_id: str
) -> dict[str, Any]:
    response = await client.post(
        f"/api/v1/accounts/{account_id}/bindings",
        headers=identity(),
        json={"deviceId": device_id, "confirmationNote": "Owner confirmed test device."},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def create_task(
    client: httpx.AsyncClient,
    device_id: str,
    *,
    key: str,
    body: dict[str, Any] | None = None,
) -> httpx.Response:
    return await client.post(
        "/api/v1/mobile/tasks",
        headers={**identity(), "Idempotency-Key": key},
        json=body or task_body(device_id),
    )


@pytest.mark.asyncio
async def test_operator_auth_rbac_and_tenant_isolation(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, _ = api
    device_id = await create_device(client)

    missing = await client.post("/api/v1/mobile/enrollments", json={"deviceId": device_id})
    assert missing.status_code == 401

    forbidden = await client.post(
        "/api/v1/mobile/enrollments",
        headers=identity(role="content_viewer"),
        json={"deviceId": device_id},
    )
    assert forbidden.status_code == 403

    cross_tenant = await client.post(
        "/api/v1/mobile/enrollments",
        headers=identity(tenant=TENANT_B),
        json={"deviceId": device_id},
    )
    assert cross_tenant.status_code == 404


@pytest.mark.asyncio
async def test_enrollment_is_one_time_expiring_and_strict(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = api
    device_id = await create_device(client)
    created = await client.post(
        "/api/v1/mobile/enrollments",
        headers=identity(),
        json={"deviceId": device_id, "ttlSeconds": 600},
    )
    code = created.json()["code"]
    payload = {
        "code": code,
        "appInstanceId": "instance-0001",
        "companionVersion": "1.0.0",
    }
    assert (await client.post("/companion/v2/enroll", json=payload)).status_code == 201
    assert (await client.post("/companion/v2/enroll", json=payload)).status_code == 401

    unknown = await client.post("/companion/v2/enroll", json={**payload, "unexpected": True})
    assert unknown.status_code == 422

    expiring = await client.post(
        "/api/v1/mobile/enrollments",
        headers=identity(),
        json={"deviceId": device_id, "ttlSeconds": 60},
    )
    database = app.state.database
    async with database.unit_of_work() as session:
        row = await session.get(MobileEnrollmentRow, expiring.json()["enrollmentId"])
        assert row is not None
        row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    expired = await client.post(
        "/companion/v2/enroll",
        json={
            "code": expiring.json()["code"],
            "appInstanceId": "instance-0002",
            "companionVersion": "1.0.0",
        },
    )
    assert expired.status_code == 401


@pytest.mark.asyncio
async def test_companion_account_status_is_bound_and_secret_free(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = api
    device_id = await create_device(client)
    token = await enroll(client, device_id)
    account_response = await client.post(
        "/api/v1/accounts",
        headers=identity(role="device_operator"),
        json={
            "platform": "authorized-platform-adapter",
            "externalSubjectRef": "mobile-status-account",
            "displayLabel": "Mobile status account",
            "secretRef": "vault://cloudctl/accounts/mobile-status",
            "authorizationBasis": "Owner authorized the test account.",
        },
    )
    assert account_response.status_code == 201, account_response.text
    account = account_response.json()
    binding = await client.post(
        f"/api/v1/accounts/{account['id']}/bindings",
        headers=identity(role="device_operator"),
        json={"deviceId": device_id, "confirmationNote": "Owner confirmed test device."},
    )
    assert binding.status_code == 201, binding.text

    status = await client.get(
        "/companion/v2/accounts/status",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert status.status_code == 200, status.text
    row = status.json()[0]
    assert row["accountId"] == account["id"]
    assert row["authorized"] is True
    assert row["boundToDevice"] is True
    assert "secretRef" not in row
    assert "externalSubjectRef" not in row

    database = app.state.database
    async with database.unit_of_work() as session:
        stored = await session.get(PlatformAccountRow, account["id"])
        assert stored is not None
        stored.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    expired = await client.get(
        "/companion/v2/accounts/status",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert expired.status_code == 200
    assert expired.json()[0]["authorized"] is False


@pytest.mark.asyncio
async def test_companion_bearer_cannot_use_operator_api(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, _ = api
    device_id = await create_device(client)
    token = await enroll(client, device_id)
    response = await client.get(
        "/api/v1/mobile/tasks", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutation",
    [
        lambda body: body["steps"][0].update({"action": "shell"}),
        lambda body: body["steps"][1].update({"x": 1, "y": 2}),
        lambda body: body["steps"][1].pop("locatorRef"),
        lambda body: body.update({"targetPackage": "invalid"}),
        lambda body: body.update({"unknown": True}),
        lambda body: body.update({"totalTimeoutMs": 1_000}),
        lambda body: body.update(
            {
                "steps": [
                    {
                        "stepId": f"step-{index}",
                        "action": "ui.screenshot",
                        "label": f"shot-{index}",
                        "timeoutMs": 100,
                    }
                    for index in range(101)
                ]
            }
        ),
        lambda body: body.update(
            {
                "steps": [
                    {
                        "stepId": "input-value",
                        "action": "ui.input",
                        "locatorRef": "screen.input",
                        "value": "x" * 1025,
                        "timeoutMs": 1_000,
                    }
                ]
            }
        ),
        lambda body: body.update(
            {
                "steps": [
                    {
                        "stepId": "log-event",
                        "action": "run.log",
                        "messageCode": "STEP_DONE",
                        "attributes": {"accessToken": "not-allowed"},
                        "timeoutMs": 1_000,
                    }
                ]
            }
        ),
    ],
)
async def test_task_schema_rejects_unsafe_or_unbounded_content(
    api: tuple[httpx.AsyncClient, FastAPI], mutation: Any
) -> None:
    client, _ = api
    device_id = await create_device(client)
    body = copy.deepcopy(task_body(device_id))
    mutation(body)
    response = await create_task(client, device_id, key=str(uuid.uuid4()), body=body)
    assert response.status_code == 422, response.text


@pytest.mark.asyncio
async def test_task_accepts_companion_target_without_server_locator_whitelist(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, _ = api
    device_id = await create_device(client)
    body = copy.deepcopy(task_body(device_id))
    body["steps"][0]["locatorRef"] = "compiled.module.entry"
    body["steps"][1]["locatorRef"] = "compiled.module.entry"
    body["steps"][1]["postconditionLocatorRef"] = "compiled.module.ready"
    response = await create_task(client, device_id, key=str(uuid.uuid4()), body=body)
    assert response.status_code == 201, response.text


@pytest.mark.asyncio
async def test_task_idempotency_listing_and_cross_tenant_detail(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, _ = api
    device_id = await create_device(client)
    first = await create_task(client, device_id, key="same-key")
    assert first.status_code == 201, first.text
    replay = await create_task(client, device_id, key="same-key")
    assert replay.status_code == 200
    assert replay.headers["Idempotency-Replayed"] == "true"
    assert replay.json()["taskId"] == first.json()["taskId"]

    changed = task_body(device_id)
    changed["totalTimeoutMs"] = 31_000
    conflict = await create_task(client, device_id, key="same-key", body=changed)
    assert conflict.status_code == 409

    listed = await client.get("/api/v1/mobile/tasks", headers=identity())
    assert listed.status_code == 200
    assert [item["taskId"] for item in listed.json()] == [first.json()["taskId"]]
    detail = await client.get(f"/api/v1/mobile/tasks/{first.json()['taskId']}", headers=identity())
    assert detail.status_code == 200
    assert detail.json()["events"] == []
    assert detail.json()["createdAt"] is not None
    hidden = await client.get(
        f"/api/v1/mobile/tasks/{first.json()['taskId']}",
        headers=identity(tenant=TENANT_B),
    )
    assert hidden.status_code == 404


@pytest.mark.asyncio
async def test_claim_rounds_partial_seconds_up(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, _ = api
    device_id = await create_device(client)
    token = await enroll(client, device_id)
    body = task_body(device_id)
    body["totalTimeoutMs"] = 5_500
    body["steps"] = [body["steps"][0]]
    created = await create_task(client, device_id, key="partial-second", body=body)
    assert created.status_code == 201, created.text
    claimed = await client.post(
        "/companion/v2/tasks/claim",
        headers={"Authorization": f"Bearer {token}"},
        json={"leaseSeconds": 60},
    )
    assert claimed.status_code == 200
    assert claimed.json()["maxRunSeconds"] == 6


@pytest.mark.asyncio
async def test_mobile_direct_device_enrolls_without_edge(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, _ = api
    device_id = await create_direct_device(client)
    token = await enroll(client, device_id)
    response = await client.post(
        "/companion/v2/tasks/claim",
        headers={"Authorization": f"Bearer {token}"},
        json={"leaseSeconds": 60},
    )
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_claim_heartbeat_single_active_and_expired_lease_recovery(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = api
    device_id = await create_device(client)
    token = await enroll(client, device_id)
    auth = {"Authorization": f"Bearer {token}"}

    empty = await client.post("/companion/v2/tasks/claim", headers=auth, json={"leaseSeconds": 60})
    assert empty.status_code == 204
    assert empty.content == b""

    first = await create_task(client, device_id, key="task-1")
    await create_task(client, device_id, key="task-2")
    claimed = await client.post(
        "/companion/v2/tasks/claim", headers=auth, json={"leaseSeconds": 60}
    )
    assert claimed.status_code == 200
    assert claimed.json()["taskId"] == first.json()["taskId"]
    assert claimed.json()["protocolVersion"] == "cloudctl.mobile/v1"
    assert claimed.json()["maxRunSeconds"] == 30

    blocked = await client.post(
        "/companion/v2/tasks/claim", headers=auth, json={"leaseSeconds": 60}
    )
    assert blocked.status_code == 204

    heartbeat = await client.post(
        f"/companion/v2/tasks/{claimed.json()['taskId']}/heartbeat",
        headers=auth,
        json={
            "leaseId": claimed.json()["leaseId"],
            "currentStep": 0,
            "leaseSeconds": 120,
        },
    )
    assert heartbeat.status_code == 200
    assert heartbeat.json()["status"] == "RUNNING"
    assert heartbeat.json()["currentStep"] == 0
    assert heartbeat.json()["businessState"] == "RUNNING"
    assert heartbeat.json()["controlMode"] == "AUTO"

    database = app.state.database
    async with database.unit_of_work() as session:
        row = await session.get(MobileTaskRow, claimed.json()["taskId"])
        assert row is not None
        row.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    reclaimed = await client.post(
        "/companion/v2/tasks/claim", headers=auth, json={"leaseSeconds": 60}
    )
    assert reclaimed.status_code == 200
    assert reclaimed.json()["taskId"] == claimed.json()["taskId"]
    assert reclaimed.json()["leaseId"] != claimed.json()["leaseId"]
    assert reclaimed.json()["attempt"] == 2
    assert claimed.json().get("controlEpoch") or reclaimed.json().get("controlEpoch")


@pytest.mark.asyncio
async def test_event_order_replay_completion_failure_and_unbind(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, _ = api
    device_id = await create_device(client)
    token = await enroll(client, device_id)
    auth = {"Authorization": f"Bearer {token}"}
    task = await create_task(client, device_id, key="event-task")
    claimed = await client.post(
        "/companion/v2/tasks/claim", headers=auth, json={"leaseSeconds": 60}
    )
    task_id = task.json()["taskId"]
    lease_id = claimed.json()["leaseId"]
    event = {
        "leaseId": lease_id,
        "sequence": 1,
        "eventType": "STEP_STARTED",
        "stepIndex": 0,
        "payload": {"state": "started"},
    }
    created = await client.post(f"/companion/v2/tasks/{task_id}/events", headers=auth, json=event)
    assert created.status_code == 201
    replay = await client.post(f"/companion/v2/tasks/{task_id}/events", headers=auth, json=event)
    assert replay.status_code == 200
    assert replay.headers["Idempotency-Replayed"] == "true"

    changed = await client.post(
        f"/companion/v2/tasks/{task_id}/events",
        headers=auth,
        json={**event, "payload": {"state": "different"}},
    )
    assert changed.status_code == 409
    gap = await client.post(
        f"/companion/v2/tasks/{task_id}/events",
        headers=auth,
        json={**event, "sequence": 3},
    )
    assert gap.status_code == 409
    sensitive = await client.post(
        f"/companion/v2/tasks/{task_id}/events",
        headers=auth,
        json={**event, "sequence": 2, "payload": {"password": "redacted"}},
    )
    assert sensitive.status_code == 422

    completed = await client.post(
        f"/companion/v2/tasks/{task_id}/complete",
        headers=auth,
        json={"leaseId": lease_id, "result": {"outcome": "ok"}},
    )
    assert completed.status_code == 200
    assert completed.json()["status"] == "SUCCEEDED"
    assert completed.json()["completedAt"] is not None
    completed_replay = await client.post(
        f"/companion/v2/tasks/{task_id}/complete",
        headers=auth,
        json={"leaseId": lease_id, "result": {"outcome": "ok"}},
    )
    assert completed_replay.status_code == 200
    conflicting_completion = await client.post(
        f"/companion/v2/tasks/{task_id}/complete",
        headers=auth,
        json={"leaseId": lease_id, "result": {"outcome": "different"}},
    )
    assert conflicting_completion.status_code == 409

    second = await create_task(client, device_id, key="failed-task")
    second_claim = await client.post(
        "/companion/v2/tasks/claim", headers=auth, json={"leaseSeconds": 60}
    )
    failed = await client.post(
        f"/companion/v2/tasks/{second.json()['taskId']}/fail",
        headers=auth,
        json={
            "leaseId": second_claim.json()["leaseId"],
            "errorCode": "ASSERT_FAILED",
            "detail": "expected element was not found",
        },
    )
    assert failed.status_code == 200
    assert failed.json()["status"] == "FAILED"
    failed_replay = await client.post(
        f"/companion/v2/tasks/{second.json()['taskId']}/fail",
        headers=auth,
        json={
            "leaseId": second_claim.json()["leaseId"],
            "errorCode": "ASSERT_FAILED",
            "detail": "expected element was not found",
        },
    )
    assert failed_replay.status_code == 200

    detail = await client.get(f"/api/v1/mobile/tasks/{task_id}", headers=identity())
    assert [item["sequence"] for item in detail.json()["events"]] == [1]

    unbound = await client.delete("/companion/v2/binding", headers=auth)
    assert unbound.status_code == 204
    rejected = await client.post(
        "/companion/v2/tasks/claim", headers=auth, json={"leaseSeconds": 60}
    )
    assert rejected.status_code == 401


@pytest.mark.asyncio
async def test_device_heartbeat_marks_last_seen_without_changing_task_state(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, _ = api
    device_id = await create_direct_device(client)
    token = await enroll(client, device_id)
    auth = {"Authorization": f"Bearer {token}"}

    listed = await client.get("/api/v1/devices", headers=identity(role="security_admin"))
    assert listed.status_code == 200
    record = next(item for item in listed.json() if item["id"] == device_id)
    assert record["state"] == "REGISTERED"
    assert record["last_seen_at"] is not None

    heartbeat = await client.post(
        "/companion/v2/devices/heartbeat",
        headers=auth,
        json={
            "companionVersion": "0.1.0",
            "androidVersion": "14",
            "accessibilityEnabled": True,
            "runnerState": "IDLE",
            "batteryOptimizationIgnored": False,
            "health": {
                "batteryPercent": 100,
                "charging": True,
                "network": "CELLULAR",
                "temperatureCelsius": 33.0,
                "freeStorageBytes": 1000,
            },
        },
    )
    assert heartbeat.status_code == 200, heartbeat.text
    assert heartbeat.json()["ok"] is True
    assert heartbeat.json()["deviceId"] == device_id

    refreshed = await client.get("/api/v1/devices", headers=identity(role="security_admin"))
    updated = next(item for item in refreshed.json() if item["id"] == device_id)
    assert updated["state"] == "REGISTERED"
    assert updated["last_seen_at"] is not None
    assert updated["android_version"] == "14"
    assert updated["capabilities"]["runnerState"] == "IDLE"
    assert updated["capabilities"]["accessibilityEnabled"] is True
    assert updated["capabilities"]["batteryOptimizationIgnored"] is False

    rejected = await client.post(
        "/companion/v2/devices/heartbeat",
        json={
            "companionVersion": "0.1.0",
            "accessibilityEnabled": True,
            "runnerState": "IDLE",
        },
    )
    assert rejected.status_code == 401


@pytest.mark.asyncio
async def test_xianyu_text_publish_task_is_accepted_and_claimable(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, _ = api
    device_id = await create_direct_device(client)
    token = await enroll(client, device_id)
    body = build_text_publish_task(
        device_id,
        description="自用闲置，功能正常，支持当面交易",
        price="128",
    )
    created = await create_task(client, device_id, key="xianyu-text-publish", body=body)
    assert created.status_code == 201, created.text
    assert created.json()["targetPackage"] == XIANYU_PACKAGE
    assert [step["stepId"] for step in created.json()["steps"]] == [
        "find-home-sell",
        "open-sell",
        "open-publish",
        "wait-publish-page",
        "wait-description",
        "fill-description",
        "confirm-description",
        "wait-price",
        "fill-price",
        "capture-form",
        "mark-ready",
    ]

    claimed = await client.post(
        "/companion/v2/tasks/claim",
        headers={"Authorization": f"Bearer {token}"},
        json={"leaseSeconds": 60},
    )
    assert claimed.status_code == 200, claimed.text
    payload = claimed.json()
    assert payload["protocolVersion"] == "cloudctl.mobile/v1"
    assert payload["targetPackage"] == XIANYU_PACKAGE
    assert payload.get("commandType") in (None, "xianyu.publish_listing.v1")
    assert payload["steps"][5]["value"] == "自用闲置，功能正常，支持当面交易"
    assert payload["steps"][8]["value"] == "128"
    assert payload["maxRunSeconds"] == (body["totalTimeoutMs"] + 999) // 1000


@pytest.mark.asyncio
async def test_companion_can_request_bound_text_publish_task(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, _ = api
    device_id = await create_direct_device(client)
    token = await enroll(client, device_id)
    response = await client.post(
        "/companion/v2/tasks/publish-listing",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "description": "自用闲置，功能正常，支持当面交易",
            "price": "128",
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["targetPackage"] == XIANYU_PACKAGE
    assert response.json()["deviceId"] == device_id
    claimed = await client.post(
        "/companion/v2/tasks/claim",
        headers={"Authorization": f"Bearer {token}"},
        json={"leaseSeconds": 60},
    )
    assert claimed.status_code == 200
    assert claimed.json()["taskId"] == response.json()["taskId"]


@pytest.mark.asyncio
async def test_xianyu_publish_attaches_tenant_owned_media_delivery(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, _ = api
    device_id = await create_direct_device(client)
    asset = await client.post(
        "/api/v1/media/assets:register",
        headers=identity(role="content_editor"),
        json={
            "sha256": "d" * 64,
            "objectKey": "listing/cover.jpg",
            "contentType": "image/jpeg",
            "sizeBytes": 12,
        },
    )
    assert asset.status_code == 201, asset.text
    asset_id = asset.json()["id"]
    body = build_text_publish_task(
        device_id,
        description="自用闲置，功能正常，支持当面交易",
        price="128",
        media_asset_ids=[asset_id],
        delivery_id="delivery-xianyu-1",
    )
    response = await create_task(client, device_id, key=str(uuid.uuid4()), body=body)
    assert response.status_code == 201, response.text
    assert response.json()["mediaDelivery"] == {
        "deliveryId": "delivery-xianyu-1",
        "assetIds": [asset_id],
    }

    token = await enroll(client, device_id)
    claimed = await client.post(
        "/companion/v2/tasks/claim",
        headers={"Authorization": f"Bearer {token}"},
        json={"leaseSeconds": 60},
    )
    assert claimed.status_code == 200, claimed.text
    assert claimed.json()["mediaDelivery"]["deliveryId"] == "delivery-xianyu-1"
    assert claimed.json()["mediaDelivery"]["assetIds"] == [asset_id]


@pytest.mark.asyncio
async def test_xianyu_publish_rejects_unknown_media_asset(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, _ = api
    device_id = await create_direct_device(client)
    body = build_text_publish_task(
        device_id,
        description="自用闲置，功能正常，支持当面交易",
        price="128",
        media_asset_ids=["missing-asset"],
        delivery_id="delivery-xianyu-missing",
    )
    response = await create_task(client, device_id, key=str(uuid.uuid4()), body=body)
    assert response.status_code == 404, response.text


PREVIEW_JPEG = b"\xff\xd8\xff\xe0" + b"cloudctl-preview-frame" * 12 + b"\xff\xd9"


@pytest.mark.asyncio
async def test_companion_preview_session_round_trip(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, _ = api
    device_id = await create_direct_device(client)
    token = await enroll(client, device_id)
    auth = {"Authorization": f"Bearer {token}"}

    heartbeat = await client.post(
        "/companion/v2/devices/heartbeat",
        headers=auth,
        json={
            "companionVersion": "0.1.0",
            "accessibilityEnabled": True,
            "runnerState": "IDLE",
        },
    )
    assert heartbeat.status_code == 200, heartbeat.text
    assert heartbeat.json()["preview"] is None

    forbidden = await client.post(
        f"/api/v1/mobile/devices/{device_id}/preview/sessions",
        headers=identity(role="viewer"),
        json={"ttlSeconds": 120},
    )
    assert forbidden.status_code == 403

    started = await client.post(
        f"/api/v1/mobile/devices/{device_id}/preview/sessions",
        headers=identity(),
        json={"ttlSeconds": 90, "captureIntervalMs": 2000},
    )
    assert started.status_code == 201, started.text
    session_id = started.json()["sessionId"]
    assert started.json()["active"] is True
    assert started.json()["waitingForFrame"] is True

    heartbeat = await client.post(
        "/companion/v2/devices/heartbeat",
        headers=auth,
        json={
            "companionVersion": "0.1.0",
            "accessibilityEnabled": True,
            "runnerState": "IDLE",
        },
    )
    assert heartbeat.json()["preview"]["sessionId"] == session_id
    assert heartbeat.json()["preview"]["captureIntervalMs"] == 2000

    digest = hashlib.sha256(PREVIEW_JPEG).hexdigest()
    uploaded = await client.post(
        "/companion/v2/devices/preview",
        headers=auth,
        json={
            "sessionId": session_id,
            "contentType": "image/jpeg",
            "sha256": digest,
            "width": 720,
            "height": 1280,
            "imageBase64": base64.b64encode(PREVIEW_JPEG).decode("ascii"),
        },
    )
    assert uploaded.status_code == 200, uploaded.text
    assert uploaded.json()["waitingForFrame"] is False
    assert uploaded.json()["sha256"] == digest

    status = await client.get(
        f"/api/v1/mobile/devices/{device_id}/preview",
        headers=identity(role="viewer"),
    )
    assert status.status_code == 200
    assert status.json()["hasFrame"] is True
    assert status.json()["sha256"] == digest

    frame = await client.get(
        f"/api/v1/mobile/devices/{device_id}/preview/frame",
        headers=identity(role="viewer"),
    )
    assert frame.status_code == 200
    assert frame.headers["content-type"].startswith("image/jpeg")
    assert frame.content == PREVIEW_JPEG

    cached = await client.get(
        f"/api/v1/mobile/devices/{device_id}/preview/frame",
        headers={**identity(role="viewer"), "If-None-Match": frame.headers["etag"]},
    )
    assert cached.status_code == 304

    mismatched = await client.post(
        "/companion/v2/devices/preview",
        headers=auth,
        json={
            "sessionId": str(uuid.uuid4()),
            "contentType": "image/jpeg",
            "sha256": digest,
            "width": 720,
            "height": 1280,
            "imageBase64": base64.b64encode(PREVIEW_JPEG).decode("ascii"),
        },
    )
    assert mismatched.status_code == 409

    stopped = await client.post(
        f"/api/v1/mobile/devices/{device_id}/preview/sessions/{session_id}:stop",
        headers=identity(),
    )
    assert stopped.status_code == 200
    assert stopped.json()["active"] is False

    heartbeat = await client.post(
        "/companion/v2/devices/heartbeat",
        headers=auth,
        json={
            "companionVersion": "0.1.0",
            "accessibilityEnabled": True,
            "runnerState": "IDLE",
        },
    )
    assert heartbeat.json()["preview"] is None


@pytest.mark.asyncio
async def test_reenroll_revokes_previous_companion_instance(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, _ = api
    device_id = await create_direct_device(client)
    first = await enroll(client, device_id, instance="instance-a")
    second = await enroll(client, device_id, instance="instance-b")
    stale = await client.post(
        "/companion/v2/devices/heartbeat",
        headers={"Authorization": f"Bearer {first}"},
        json={
            "companionVersion": "0.1.0",
            "accessibilityEnabled": True,
            "runnerState": "IDLE",
        },
    )
    assert stale.status_code == 401
    live = await client.post(
        "/companion/v2/devices/heartbeat",
        headers={"Authorization": f"Bearer {second}"},
        json={
            "companionVersion": "0.1.1",
            "androidVersion": "10",
            "accessibilityEnabled": True,
            "runnerState": "IDLE",
            "health": {
                "network": "CELLULAR",
                "manufacturer": "Xiaomi",
                "model": "Redmi Note 9",
                "sdkInt": 29,
                "mediaProjection": "UNKNOWN",
            },
        },
    )
    assert live.status_code == 200, live.text


@pytest.mark.asyncio
async def test_rebind_fails_queued_task_with_account_changed(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, _ = api
    device_id = await create_direct_device(client)
    token = await enroll(client, device_id)
    account_a = await create_account(client, platform="xianyu", subject="xy-a", label="闲鱼甲")
    account_b = await create_account(client, platform="xianyu", subject="xy-b", label="闲鱼乙")
    bound = await bind_account(client, account_a, device_id)
    body = {
        **task_body(device_id),
        "accountId": account_a,
        "expectedBindingVersion": bound["bindingVersion"],
    }
    created = await create_task(client, device_id, key="owned-by-a", body=body)
    assert created.status_code == 201, created.text
    assert created.json()["accountId"] == account_a
    assert created.json()["bindingVersion"] == bound["bindingVersion"]

    rebound = await bind_account(client, account_b, device_id)
    assert rebound["accountId"] == account_b

    claimed = await client.post(
        "/companion/v2/tasks/claim",
        headers={"Authorization": f"Bearer {token}"},
        json={"leaseSeconds": 60},
    )
    assert claimed.status_code == 204, claimed.text

    detail = await client.get(
        f"/api/v1/mobile/tasks/{created.json()['taskId']}", headers=identity()
    )
    assert detail.status_code == 200, detail.text
    assert detail.json()["status"] == "FAILED"
    assert detail.json()["errorCode"] == "ACCOUNT_CHANGED"
    assert detail.json()["accountId"] == account_a

    ownership = await client.get(f"/api/v1/accounts/{account_a}/ownership", headers=identity())
    assert ownership.status_code == 200, ownership.text
    assert ownership.json()["unbound"] is True
    assert ownership.json()["mobileTasks"][0]["accountId"] == account_a
    assert ownership.json()["mobileTasks"][0]["errorCode"] == "ACCOUNT_CHANGED"


@pytest.mark.asyncio
async def test_paused_head_blocks_later_task_and_maintenance_blocks_auto_claim(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = api
    device_id = await create_direct_device(client)
    token = await enroll(client, device_id)
    first = await create_task(client, device_id, key="paused-head")
    second = await create_task(client, device_id, key="later-task")
    async with app.state.database.unit_of_work() as session:
        row = await session.get(MobileTaskRow, first.json()["taskId"])
        assert row is not None
        row.business_state = "PAUSED_WAITING_USER"
        row.status = "QUEUED"
    blocked = await client.post(
        "/companion/v2/tasks/claim",
        headers={"Authorization": f"Bearer {token}"},
        json={"leaseSeconds": 60},
    )
    assert blocked.status_code == 204
    async with app.state.database.unit_of_work() as session:
        later = await session.get(MobileTaskRow, second.json()["taskId"])
        assert later is not None
        assert later.status == "QUEUED"

    other_device = await client.post(
        "/api/v1/mobile/devices",
        headers=identity(),
        json={
            "logicalName": "oneplus-9r-maint",
            "androidVersion": "14",
            "companionVersion": "1.0.0",
            "labels": ["mobile-direct"],
        },
    )
    assert other_device.status_code == 201, other_device.text
    other = str(other_device.json()["id"])
    other_token = await enroll(client, other, instance="instance-maint")
    await create_task(client, other, key="maint-task")
    hold = await client.post(
        f"/api/v1/devices/{other}:maintenance",
        headers=identity(role="security_admin"),
        json={"enabled": True, "reason": "operator locked device for maintenance"},
    )
    assert hold.status_code == 200, hold.text
    denied = await client.post(
        "/companion/v2/tasks/claim",
        headers={"Authorization": f"Bearer {other_token}"},
        json={"leaseSeconds": 60},
    )
    assert denied.status_code == 409
