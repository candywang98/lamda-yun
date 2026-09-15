from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from cloudctl_api import create_app
from cloudctl_api.settings import Settings
from fastapi import FastAPI
from sqlalchemy import select

TENANT = "00000000-0000-7000-8000-000000000111"
OPERATOR = "00000000-0000-7000-8000-000000000222"


def identity(*, role: str = "device_operator") -> dict[str, str]:
    return {
        "X-Tenant-Id": TENANT,
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


async def create_direct_device(client: httpx.AsyncClient, name: str) -> str:
    response = await client.post(
        "/api/v1/mobile/devices",
        headers=identity(),
        json={"logicalName": name, "androidVersion": "14", "companionVersion": "1.0.0"},
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


async def create_account(client: httpx.AsyncClient, subject: str) -> str:
    response = await client.post(
        "/api/v1/accounts",
        headers=identity(),
        json={
            "platform": "xianyu",
            "externalSubjectRef": subject,
            "displayLabel": subject,
            "secretRef": f"vault://cloudctl/accounts/{subject}",
            "authorizationBasis": "Owner authorized the test account.",
        },
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


async def bind(client: httpx.AsyncClient, account_id: str, device_id: str) -> dict[str, Any]:
    response = await client.post(
        f"/api/v1/accounts/{account_id}/bindings",
        headers=identity(),
        json={"deviceId": device_id, "confirmationNote": "Owner confirmed."},
    )
    assert response.status_code == 201, response.text
    return response.json()


PROBE = {
    "commandType": "device.probe_capabilities.v1",
    "parameters": {},
}


@pytest.mark.asyncio
async def test_platform_task_idempotency_pagination_and_device_isolation(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, _ = api
    device_a = await create_direct_device(client, "phone-a")
    device_b = await create_direct_device(client, "phone-b")
    account = await create_account(client, "xy-owner")
    bound = await bind(client, account, device_a)
    await bind(client, account, device_b)

    first = await client.post(
        "/api/v1/platform-tasks",
        headers={**identity(), "Idempotency-Key": "click-once"},
        json={"deviceId": device_a, "accountId": account, "expectedBindingVersion": bound["bindingVersion"], **PROBE},
    )
    assert first.status_code == 201, first.text
    replay = await client.post(
        "/api/v1/platform-tasks",
        headers={**identity(), "Idempotency-Key": "click-once"},
        json={"deviceId": device_a, "accountId": account, "expectedBindingVersion": bound["bindingVersion"], **PROBE},
    )
    assert replay.status_code == 200
    assert replay.json()["items"][0]["taskId"] == first.json()["items"][0]["taskId"]
    conflict = await client.post(
        "/api/v1/platform-tasks",
        headers={**identity(), "Idempotency-Key": "click-once"},
        json={
            "deviceId": device_a,
            "accountId": account,
            "commandType": "xianyu.collect_orders.v1",
            "parameters": {"role": "ALL_VISIBLE", "limit": 10},
        },
    )
    assert conflict.status_code == 409

    batch = await client.post(
        "/api/v1/platform-tasks",
        headers={**identity(), "Idempotency-Key": "two-phones"},
        json={
            "deviceIds": [device_a, device_b],
            "accountId": account,
            "batchId": "batch-parallel",
            **PROBE,
        },
    )
    assert batch.status_code == 201, batch.text
    assert batch.json()["count"] == 2
    ids = {item["deviceId"] for item in batch.json()["items"]}
    assert ids == {device_a, device_b}
    assert len({item["taskId"] for item in batch.json()["items"]}) == 2

    for index in range(5):
        created = await client.post(
            "/api/v1/platform-tasks",
            headers={**identity(), "Idempotency-Key": f"page-{index}"},
            json={"deviceId": device_a, "accountId": account, **PROBE},
        )
        assert created.status_code == 201, created.text

    page1 = await client.get("/api/v1/platform-tasks", headers=identity(), params={"limit": 3})
    assert page1.status_code == 200, page1.text
    assert len(page1.json()["items"]) == 3
    assert page1.json()["nextCursor"]
    page2 = await client.get(
        "/api/v1/platform-tasks",
        headers=identity(),
        params={"limit": 3, "after": page1.json()["nextCursor"]},
    )
    assert page2.status_code == 200
    first_ids = {item["taskId"] for item in page1.json()["items"]}
    second_ids = {item["taskId"] for item in page2.json()["items"]}
    assert first_ids.isdisjoint(second_ids)

    only_b = await client.get(
        "/api/v1/platform-tasks", headers=identity(), params={"deviceId": device_b, "limit": 50}
    )
    assert {item["deviceId"] for item in only_b.json()["items"]} == {device_b}


@pytest.mark.asyncio
async def test_platform_task_cancel_and_safe_retry(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = api
    device_id = await create_direct_device(client, "phone-retry")
    account = await create_account(client, "xy-retry")
    await bind(client, account, device_id)
    created = await client.post(
        "/api/v1/platform-tasks",
        headers={**identity(), "Idempotency-Key": "cancel-me"},
        json={"deviceId": device_id, "accountId": account, **PROBE},
    )
    task_id = created.json()["items"][0]["taskId"]
    canceled = await client.post(
        f"/api/v1/platform-tasks/{task_id}:cancel",
        headers=identity(),
        json={"reason": "operator stopped before claim"},
    )
    assert canceled.status_code == 200, canceled.text
    assert canceled.json()["state"] == "CANCELLED"
    replay = await client.post(
        f"/api/v1/platform-tasks/{task_id}:cancel",
        headers=identity(),
        json={"reason": "operator stopped before claim"},
    )
    assert replay.status_code == 200
    assert replay.json()["state"] == "CANCELLED"

    failed = await client.post(
        "/api/v1/platform-tasks",
        headers={**identity(), "Idempotency-Key": "fail-me"},
        json={"deviceId": device_id, "accountId": account, **PROBE},
    )
    failed_id = failed.json()["items"][0]["taskId"]
    async with app.state.database.unit_of_work() as session:
        from cloudctl_api.db import MobileTaskRow

        row = await session.get(MobileTaskRow, failed_id)
        assert row is not None
        row.status = "FAILED"
        row.business_state = "FAILED"
        row.error_code = "ACCOUNT_CHANGED"
    blocked = await client.post(
        f"/api/v1/platform-tasks/{failed_id}:retry",
        headers=identity(),
        json={"reason": "do not follow new account"},
    )
    assert blocked.status_code == 409

    async with app.state.database.unit_of_work() as session:
        from cloudctl_api.db import MobileTaskRow

        row = await session.get(MobileTaskRow, failed_id)
        assert row is not None
        row.error_code = "STEP_TIMEOUT"
    retried = await client.post(
        f"/api/v1/platform-tasks/{failed_id}:retry",
        headers=identity(),
        json={"reason": "safe timeout retry"},
    )
    assert retried.status_code == 200, retried.text
    assert retried.json()["taskId"] != failed_id
    assert retried.json()["state"] == "QUEUED"
    assert retried.json()["accountId"] == account
    assert retried.json()["snapshotSha256"]
    assert retried.json()["commandPayload"]["parameters"] == PROBE["parameters"]


@pytest.mark.asyncio
async def test_pause_event_is_not_failed_and_wrong_result_type_rejected(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, _ = api
    device_id = await create_direct_device(client, "phone-events")
    account = await create_account(client, "xy-events")
    await bind(client, account, device_id)
    created = await client.post(
        "/api/v1/platform-tasks",
        headers={**identity(), "Idempotency-Key": "pause-me"},
        json={"deviceId": device_id, "accountId": account, **PROBE},
    )
    task_id = created.json()["items"][0]["taskId"]
    enroll = await client.post(
        "/api/v1/mobile/enrollments",
        headers=identity(),
        json={"deviceId": device_id, "ttlSeconds": 600},
    )
    token_resp = await client.post(
        "/companion/v2/enroll",
        json={
            "code": enroll.json()["code"],
            "appInstanceId": "instance-events",
            "companionVersion": "1.0.0",
        },
    )
    token = token_resp.json()["bindingToken"]
    auth = {"Authorization": f"Bearer {token}"}
    claimed = await client.post("/companion/v2/tasks/claim", headers=auth, json={"leaseSeconds": 60})
    lease_id = claimed.json()["leaseId"]
    paused = await client.post(
        f"/companion/v2/tasks/{task_id}/events",
        headers=auth,
        json={
            "leaseId": lease_id,
            "sequence": 1,
            "eventType": "PAUSED_WAITING_USER",
            "stepIndex": 0,
            "payload": {"reason": "captcha"},
        },
    )
    assert paused.status_code == 201, paused.text
    detail = await client.get(f"/api/v1/platform-tasks/{task_id}", headers=identity())
    assert detail.json()["state"] == "PAUSED_WAITING_USER"
    assert detail.json()["runnerStatus"] != "FAILED"
    assert detail.json()["controlMode"] == "REMOTE"
    wrong = await client.post(
        f"/companion/v2/tasks/{task_id}/complete",
        headers=auth,
        json={
            "leaseId": lease_id,
            "result": {"outcome": "ok"},
            "resultType": "NotARealResult",
        },
    )
    assert wrong.status_code == 422


@pytest.mark.asyncio
async def test_xianyu_publish_complete_accepts_listing_result_type(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, _ = api
    device_id = await create_direct_device(client, "phone-publish-complete")
    account = await create_account(client, "xy-publish-complete")
    bound = await bind(client, account, device_id)
    created = await client.post(
        "/api/v1/platform-tasks",
        headers={**identity(), "Idempotency-Key": "publish-complete-type"},
        json={
            "deviceId": device_id,
            "accountId": account,
            "expectedBindingVersion": bound["bindingVersion"],
            "commandType": "xianyu.publish_listing.v1",
            "parameters": {
                "listingBody": "Notion Business 兑换券，图示价值 $240。拍下后按说明发送兑换方式。支持当面交易。",
                "price": "199",
            },
        },
    )
    assert created.status_code == 201, created.text
    task_id = created.json()["items"][0]["taskId"]
    enroll = await client.post(
        "/api/v1/mobile/enrollments",
        headers=identity(),
        json={"deviceId": device_id, "ttlSeconds": 600},
    )
    token_resp = await client.post(
        "/companion/v2/enroll",
        json={
            "code": enroll.json()["code"],
            "appInstanceId": "instance-publish-complete",
            "companionVersion": "1.0.0",
        },
    )
    auth = {"Authorization": f"Bearer {token_resp.json()['bindingToken']}"}
    claimed = await client.post("/companion/v2/tasks/claim", headers=auth, json={"leaseSeconds": 60})
    assert claimed.status_code == 200, claimed.text
    assert claimed.json()["commandType"] == "xianyu.publish_listing.v1"
    lease_id = claimed.json()["leaseId"]
    probe = await client.post(
        f"/companion/v2/tasks/{task_id}/complete",
        headers=auth,
        json={
            "leaseId": lease_id,
            "result": {
                "outcome": "ok",
                "resultType": "DeviceProbeResult",
                "schemaVersion": 1,
            },
        },
    )
    assert probe.status_code == 422, probe.text
    completed = await client.post(
        f"/companion/v2/tasks/{task_id}/complete",
        headers=auth,
        json={
            "leaseId": lease_id,
            "result": {
                "outcome": "ok",
                "resultType": "XianyuPublishListingResult",
                "schemaVersion": 1,
            },
        },
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "SUCCEEDED"
    detail = await client.get(f"/api/v1/platform-tasks/{task_id}", headers=identity())
    assert detail.json()["state"] == "SUCCEEDED"
    assert detail.json()["runnerStatus"] == "SUCCEEDED"


@pytest.mark.asyncio
async def test_unknown_result_stays_reconciling_until_unique_id(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, _ = api
    device_id = await create_direct_device(client, "phone-reconcile")
    account = await create_account(client, "xy-reconcile")
    await bind(client, account, device_id)
    created = await client.post(
        "/api/v1/platform-tasks",
        headers={**identity(), "Idempotency-Key": "unknown-complete"},
        json={"deviceId": device_id, "accountId": account, **PROBE},
    )
    task_id = created.json()["items"][0]["taskId"]
    unknown = await client.post(
        f"/api/v1/platform-tasks/{task_id}:mark-unknown",
        headers=identity(),
        json={"reason": "publish clicked but complete lost"},
    )
    assert unknown.status_code == 200, unknown.text
    assert unknown.json()["state"] == "RECONCILING"
    blocked = await client.post(
        f"/api/v1/platform-tasks/{task_id}:retry",
        headers=identity(),
        json={"reason": "must not auto retry unknown"},
    )
    assert blocked.status_code == 409
    resume_denied = await client.post(
        f"/api/v1/platform-tasks/{task_id}:resume",
        headers=identity(),
        json={"reason": "unknown result must stay stopped", "pageVerified": True},
    )
    assert resume_denied.status_code == 409
    waiting = await client.post(
        f"/api/v1/platform-tasks/{task_id}:reconcile",
        headers=identity(),
        json={"decision": "KEEP_WAITING", "evidence": "two similar listings, not unique"},
    )
    assert waiting.json()["state"] == "RECONCILING"
    missing_id = await client.post(
        f"/api/v1/platform-tasks/{task_id}:reconcile",
        headers=identity(),
        json={"decision": "CONFIRMED_APPLIED", "evidence": "looks published"},
    )
    assert missing_id.status_code == 409
    applied = await client.post(
        f"/api/v1/platform-tasks/{task_id}:reconcile",
        headers=identity(),
        json={
            "decision": "CONFIRMED_APPLIED",
            "evidence": "unique idlefish item matched snapshot",
            "platformItemId": "xy-item-9",
        },
    )
    assert applied.status_code == 200, applied.text
    assert applied.json()["state"] == "SUCCEEDED"
    assert applied.json()["reconciliation"]["history"][-1]["actorId"] == OPERATOR


@pytest.mark.asyncio
async def test_pause_ack_blocks_queue_and_resume_keeps_task_id(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, _ = api
    device_id = await create_direct_device(client, "phone-pause")
    account = await create_account(client, "xy-pause")
    await bind(client, account, device_id)
    first = await client.post(
        "/api/v1/platform-tasks",
        headers={**identity(), "Idempotency-Key": "running-one"},
        json={"deviceId": device_id, "accountId": account, **PROBE},
    )
    second = await client.post(
        "/api/v1/platform-tasks",
        headers={**identity(), "Idempotency-Key": "queued-two"},
        json={"deviceId": device_id, "accountId": account, **PROBE},
    )
    task_id = first.json()["items"][0]["taskId"]
    later_id = second.json()["items"][0]["taskId"]
    paused = await client.post(
        f"/api/v1/platform-tasks/{task_id}:pause",
        headers=identity(),
        json={"reason": "operator taking over"},
    )
    assert paused.json()["state"] == "PAUSE_REQUESTED"
    acked = await client.post(
        f"/api/v1/platform-tasks/{task_id}:ack-paused",
        headers=identity(),
        json={},
    )
    assert acked.json()["state"] == "PAUSED_WAITING_USER"
    assert acked.json()["controlMode"] == "REMOTE"
    later = await client.get(f"/api/v1/platform-tasks/{later_id}", headers=identity())
    assert later.json()["state"] == "QUEUED"
    denied = await client.post(
        f"/api/v1/platform-tasks/{task_id}:resume",
        headers=identity(),
        json={"reason": "page not checked", "pageVerified": False},
    )
    assert denied.status_code == 409
    resumed = await client.post(
        f"/api/v1/platform-tasks/{task_id}:resume",
        headers=identity(),
        json={"reason": "operator returned to publish page", "pageVerified": True},
    )
    assert resumed.status_code == 200, resumed.text
    assert resumed.json()["taskId"] == task_id
    assert resumed.json()["state"] == "RESUME_CHECK"
    assert resumed.json()["resumeCount"] == 1
    assert resumed.json()["controlMode"] == "AUTO"
    assert resumed.json()["controlEpoch"]
    later_after_resume = await client.get(f"/api/v1/platform-tasks/{later_id}", headers=identity())
    assert later_after_resume.json()["state"] == "QUEUED"


@pytest.mark.asyncio
async def test_resume_requires_ack_and_cancelled_task_cannot_continue(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, _ = api
    device_id = await create_direct_device(client, "phone-cancel-resume")
    account = await create_account(client, "xy-cancel-resume")
    await bind(client, account, device_id)
    first = await client.post(
        "/api/v1/platform-tasks",
        headers={**identity(), "Idempotency-Key": "cancel-resume-one"},
        json={"deviceId": device_id, "accountId": account, **PROBE},
    )
    second = await client.post(
        "/api/v1/platform-tasks",
        headers={**identity(), "Idempotency-Key": "cancel-resume-two"},
        json={"deviceId": device_id, "accountId": account, **PROBE},
    )
    task_id = first.json()["items"][0]["taskId"]
    later_id = second.json()["items"][0]["taskId"]
    paused = await client.post(
        f"/api/v1/platform-tasks/{task_id}:pause",
        headers=identity(),
        json={"reason": "operator taking over"},
    )
    assert paused.json()["state"] == "PAUSE_REQUESTED"
    too_early = await client.post(
        f"/api/v1/platform-tasks/{task_id}:resume",
        headers=identity(),
        json={"reason": "ack missing", "pageVerified": True},
    )
    assert too_early.status_code == 409
    acked = await client.post(
        f"/api/v1/platform-tasks/{task_id}:ack-paused",
        headers=identity(),
        json={},
    )
    assert acked.json()["state"] == "PAUSED_WAITING_USER"
    canceled = await client.post(
        f"/api/v1/platform-tasks/{task_id}:cancel",
        headers=identity(),
        json={"reason": "operator abandoned the paused task"},
    )
    assert canceled.status_code == 200, canceled.text
    assert canceled.json()["state"] == "CANCELLED"
    denied = await client.post(
        f"/api/v1/platform-tasks/{task_id}:resume",
        headers=identity(),
        json={"reason": "must not revive cancelled work", "pageVerified": True},
    )
    assert denied.status_code == 409
    later = await client.get(f"/api/v1/platform-tasks/{later_id}", headers=identity())
    assert later.json()["state"] == "QUEUED"


@pytest.mark.asyncio
async def test_succeeded_task_cannot_be_pause_acked(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = api
    device_id = await create_direct_device(client, "phone-ack-terminal")
    account = await create_account(client, "xy-ack-terminal")
    await bind(client, account, device_id)
    created = await client.post(
        "/api/v1/platform-tasks",
        headers={**identity(), "Idempotency-Key": "ack-terminal"},
        json={"deviceId": device_id, "accountId": account, **PROBE},
    )
    task_id = created.json()["items"][0]["taskId"]
    async with app.state.database.unit_of_work() as session:
        from cloudctl_api.db import MobileTaskRow

        row = await session.get(MobileTaskRow, task_id)
        assert row is not None
        row.status = "SUCCEEDED"
        row.business_state = "SUCCEEDED"
    denied = await client.post(
        f"/api/v1/platform-tasks/{task_id}:ack-paused",
        headers=identity(),
        json={},
    )
    assert denied.status_code == 409
    unknown = await client.post(
        f"/api/v1/platform-tasks/{task_id}:mark-unknown",
        headers=identity(),
        json={"reason": "already succeeded"},
    )
    assert unknown.status_code == 409


@pytest.mark.asyncio
async def test_commit_intent_pause_stays_reconciling_and_blocks_resume(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = api
    device_id = await create_direct_device(client, "phone-commit-intent")
    account = await create_account(client, "xy-commit-intent")
    await bind(client, account, device_id)
    created = await client.post(
        "/api/v1/platform-tasks",
        headers={**identity(), "Idempotency-Key": "commit-intent-pause"},
        json={"deviceId": device_id, "accountId": account, **PROBE},
    )
    task_id = created.json()["items"][0]["taskId"]
    async with app.state.database.unit_of_work() as session:
        from cloudctl_api.db import MobileTaskRow

        row = await session.get(MobileTaskRow, task_id)
        assert row is not None
        row.command_payload = {**(row.command_payload or {}), "commitIntent": True}
        row.status = "RUNNING"
        row.business_state = "PAUSE_REQUESTED"
    acked = await client.post(
        f"/api/v1/platform-tasks/{task_id}:ack-paused",
        headers=identity(),
        json={},
    )
    assert acked.status_code == 200, acked.text
    assert acked.json()["state"] == "RECONCILING"
    denied = await client.post(
        f"/api/v1/platform-tasks/{task_id}:resume",
        headers=identity(),
        json={"reason": "must not continue after commit intent", "pageVerified": True},
    )
    assert denied.status_code == 409
    retried = await client.post(
        f"/api/v1/platform-tasks/{task_id}:retry",
        headers=identity(),
        json={"reason": "must not blind retry unknown commit"},
    )
    assert retried.status_code == 409


@pytest.mark.asyncio
async def test_resume_issues_new_epoch_and_device_heartbeat_command(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, _ = api
    device_id = await create_direct_device(client, "phone-resume-hb")
    account = await create_account(client, "xy-resume-hb")
    await bind(client, account, device_id)
    created = await client.post(
        "/api/v1/platform-tasks",
        headers={**identity(), "Idempotency-Key": "resume-hb"},
        json={"deviceId": device_id, "accountId": account, **PROBE},
    )
    task_id = created.json()["items"][0]["taskId"]
    later = await client.post(
        "/api/v1/platform-tasks",
        headers={**identity(), "Idempotency-Key": "resume-hb-later"},
        json={"deviceId": device_id, "accountId": account, **PROBE},
    )
    later_id = later.json()["items"][0]["taskId"]
    enroll = await client.post(
        "/api/v1/mobile/enrollments",
        headers=identity(),
        json={"deviceId": device_id, "ttlSeconds": 600},
    )
    token = (
        await client.post(
            "/companion/v2/enroll",
            json={
                "code": enroll.json()["code"],
                "appInstanceId": "instance-resume-hb",
                "companionVersion": "1.0.0",
            },
        )
    ).json()["bindingToken"]
    auth = {"Authorization": f"Bearer {token}"}
    claimed = await client.post("/companion/v2/tasks/claim", headers=auth, json={"leaseSeconds": 60})
    old_lease = claimed.json()["leaseId"]
    paused = await client.post(
        f"/api/v1/platform-tasks/{task_id}:pause",
        headers=identity(),
        json={"reason": "operator taking over"},
    )
    assert paused.json()["state"] == "PAUSE_REQUESTED"
    ack = await client.post(
        f"/companion/v2/tasks/{task_id}/events",
        headers=auth,
        json={
            "leaseId": old_lease,
            "sequence": 1,
            "eventType": "PAUSED_WAITING_USER",
            "stepIndex": 2,
            "payload": {"reason": "operator taking over"},
        },
    )
    assert ack.status_code == 201, ack.text
    resumed = await client.post(
        f"/api/v1/platform-tasks/{task_id}:resume",
        headers=identity(),
        json={"reason": "operator returned to publish page", "pageVerified": True},
    )
    assert resumed.status_code == 200, resumed.text
    epoch = resumed.json()["controlEpoch"]
    assert resumed.json()["taskId"] == task_id
    assert resumed.json()["state"] == "RESUME_CHECK"
    assert resumed.json()["controlMode"] == "AUTO"
    assert epoch
    stale = await client.post(
        f"/companion/v2/tasks/{task_id}/heartbeat",
        headers=auth,
        json={"leaseId": old_lease, "currentStep": 2, "leaseSeconds": 60},
    )
    assert stale.status_code == 409
    presence = await client.post(
        "/companion/v2/devices/heartbeat",
        headers=auth,
        json={
            "companionVersion": "1.0.0",
            "androidVersion": "14",
            "accessibilityEnabled": True,
            "runnerState": "RUNNING",
        },
    )
    assert presence.status_code == 200, presence.text
    command = presence.json()["resume"]
    assert command["taskId"] == task_id
    assert command["leaseId"] != old_lease
    assert command["controlEpoch"] == epoch
    assert command["pageVerified"] is True
    assert command["businessState"] == "RESUME_CHECK"
    continued = await client.post(
        f"/companion/v2/tasks/{task_id}/heartbeat",
        headers=auth,
        json={"leaseId": command["leaseId"], "currentStep": 2, "leaseSeconds": 60},
    )
    assert continued.status_code == 200, continued.text
    assert continued.json()["businessState"] == "RUNNING"
    later_detail = await client.get(f"/api/v1/platform-tasks/{later_id}", headers=identity())
    assert later_detail.json()["state"] == "QUEUED"
    blocked = await client.post("/companion/v2/tasks/claim", headers=auth, json={"leaseSeconds": 60})
    assert blocked.status_code == 204
    after = await client.post(
        "/companion/v2/devices/heartbeat",
        headers=auth,
        json={
            "companionVersion": "1.0.0",
            "accessibilityEnabled": True,
            "runnerState": "RUNNING",
        },
    )
    assert after.status_code == 200
    assert after.json().get("resume") in (None, {})


@pytest.mark.asyncio
async def test_heartbeat_surfaces_pause_requested_until_companion_acks(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, _ = api
    device_id = await create_direct_device(client, "phone-hb-pause")
    account = await create_account(client, "xy-hb-pause")
    await bind(client, account, device_id)
    created = await client.post(
        "/api/v1/platform-tasks",
        headers={**identity(), "Idempotency-Key": "hb-pause"},
        json={"deviceId": device_id, "accountId": account, **PROBE},
    )
    task_id = created.json()["items"][0]["taskId"]
    enroll = await client.post(
        "/api/v1/mobile/enrollments",
        headers=identity(),
        json={"deviceId": device_id, "ttlSeconds": 600},
    )
    token = (
        await client.post(
            "/companion/v2/enroll",
            json={
                "code": enroll.json()["code"],
                "appInstanceId": "instance-hb-pause",
                "companionVersion": "1.0.0",
            },
        )
    ).json()["bindingToken"]
    auth = {"Authorization": f"Bearer {token}"}
    claimed = await client.post("/companion/v2/tasks/claim", headers=auth, json={"leaseSeconds": 60})
    lease_id = claimed.json()["leaseId"]
    later = await client.post(
        "/api/v1/platform-tasks",
        headers={**identity(), "Idempotency-Key": "hb-pause-later"},
        json={"deviceId": device_id, "accountId": account, **PROBE},
    )
    later_id = later.json()["items"][0]["taskId"]
    paused = await client.post(
        f"/api/v1/platform-tasks/{task_id}:pause",
        headers=identity(),
        json={"reason": "operator taking over"},
    )
    assert paused.json()["state"] == "PAUSE_REQUESTED"
    heartbeat = await client.post(
        f"/companion/v2/tasks/{task_id}/heartbeat",
        headers=auth,
        json={"leaseId": lease_id, "currentStep": 2, "leaseSeconds": 60},
    )
    assert heartbeat.status_code == 200, heartbeat.text
    assert heartbeat.json()["status"] == "RUNNING"
    assert heartbeat.json()["businessState"] == "PAUSE_REQUESTED"
    assert heartbeat.json()["stallReason"] == "operator taking over"
    ack = await client.post(
        f"/companion/v2/tasks/{task_id}/events",
        headers=auth,
        json={
            "leaseId": lease_id,
            "sequence": 1,
            "eventType": "PAUSED_WAITING_USER",
            "stepIndex": 2,
            "payload": {"reason": "operator taking over"},
        },
    )
    assert ack.status_code == 201, ack.text
    detail = await client.get(f"/api/v1/platform-tasks/{task_id}", headers=identity())
    assert detail.json()["state"] == "PAUSED_WAITING_USER"
    assert detail.json()["controlMode"] == "REMOTE"
    blocked = await client.post("/companion/v2/tasks/claim", headers=auth, json={"leaseSeconds": 60})
    assert blocked.status_code == 204
    later_detail = await client.get(f"/api/v1/platform-tasks/{later_id}", headers=identity())
    assert later_detail.json()["state"] == "QUEUED"


@pytest.mark.asyncio
async def test_xianyu_publish_freezes_catalog_product_copy_and_cover(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, _ = api
    device_id = await create_direct_device(client, "phone-notion")
    account = await create_account(client, "xy-notion")
    bound = await bind(client, account, device_id)
    editor = identity(role="content_editor")
    asset = await client.post(
        "/api/v1/media/assets:register",
        headers=editor,
        json={
            "sha256": "c" * 64,
            "objectKey": "tenant/products/notion.jpg",
            "contentType": "image/jpeg",
            "sizeBytes": 12,
        },
    )
    assert asset.status_code == 201, asset.text
    product = await client.post(
        "/api/v1/products",
        headers=editor,
        json={
            "spuCode": "SPU-NOTION-TEST",
            "title": "Notion Business 一年免费兑换",
            "description": "Notion Business 兑换券，图示价值 $240。拍下后按说明发送兑换方式。支持当面交易。",
            "category": "虚拟",
            "price": "199",
            "stock": 1,
            "mediaAssetIds": [asset.json()["id"]],
        },
    )
    assert product.status_code == 201, product.text
    created = await client.post(
        "/api/v1/platform-tasks",
        headers={**identity(), "Idempotency-Key": "catalog-notion"},
        json={
            "deviceId": device_id,
            "accountId": account,
            "expectedBindingVersion": bound["bindingVersion"],
            "commandType": "xianyu.publish_listing.v1",
            "productId": product.json()["id"],
            "parameters": {"listingBody": "这段文案必须被商品库覆盖", "price": "9.9"},
        },
    )
    assert created.status_code == 201, created.text
    task = created.json()["items"][0]
    payload = task["commandPayload"]["parameters"]
    assert payload["listingBody"] == product.json()["description"]
    assert payload["price"] == "199"
    assert payload["mediaAssetIds"] == [asset.json()["id"]]
    assert payload["productId"] == product.json()["id"]
    assert task["commandPayload"]["mediaDeliveryId"]

    detail = await client.get(f"/api/v1/mobile/tasks/{task['taskId']}", headers=identity())
    assert detail.status_code == 200, detail.text
    step_ids = [step["stepId"] for step in detail.json()["steps"]]
    assert "select-media-0" in step_ids
    assert "confirm-crop" in step_ids
    fill = next(step for step in detail.json()["steps"] if step["stepId"] == "fill-description")
    price = next(step for step in detail.json()["steps"] if step["stepId"] == "fill-price")
    assert fill["value"] == product.json()["description"]
    assert price["value"] == "199"
    assert "AI帮你写" not in fill["value"]


async def _enroll(client: httpx.AsyncClient, device_id: str, instance: str) -> dict[str, str]:
    enroll = await client.post(
        "/api/v1/mobile/enrollments",
        headers=identity(),
        json={"deviceId": device_id, "ttlSeconds": 600},
    )
    token_resp = await client.post(
        "/companion/v2/enroll",
        json={
            "code": enroll.json()["code"],
            "appInstanceId": instance,
            "companionVersion": "1.0.0",
        },
    )
    return {"Authorization": f"Bearer {token_resp.json()['bindingToken']}"}


async def _claim_platform_probe(
    client: httpx.AsyncClient, suffix: str
) -> tuple[str, str, dict[str, str], dict[str, Any]]:
    device_id = await create_direct_device(client, f"phone-release-{suffix}")
    account_id = await create_account(client, f"xy-release-{suffix}")
    binding = await bind(client, account_id, device_id)
    created = await client.post(
        "/api/v1/platform-tasks",
        headers={**identity(), "Idempotency-Key": f"release-{suffix}"},
        json={
            "deviceId": device_id,
            "accountId": account_id,
            "expectedBindingVersion": binding["bindingVersion"],
            **PROBE,
        },
    )
    assert created.status_code == 201, created.text
    task_id = created.json()["items"][0]["taskId"]
    auth = await _enroll(client, device_id, f"instance-release-{suffix}")
    claimed = await client.post(
        "/companion/v2/tasks/claim", headers=auth, json={"leaseSeconds": 60}
    )
    assert claimed.status_code == 200, claimed.text
    assert claimed.json()["taskId"] == task_id
    return task_id, device_id, auth, claimed.json()


@pytest.mark.asyncio
async def test_companion_release_requeues_and_reclaim_mints_new_lease(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    from cloudctl_api.db import DeviceLeaseRow, MobileTaskEventRow, MobileTaskRow

    client, app = api
    task_id, device_id, auth, claimed = await _claim_platform_probe(client, "reclaim")
    old_lease = claimed["leaseId"]
    before = {
        "attempt": claimed["attempt"],
        "attemptId": claimed["attemptId"],
        "deviceIdAtExecution": claimed["deviceIdAtExecution"],
        "startedAt": claimed["startedAt"],
    }
    async with app.state.database.unit_of_work() as session:
        task = await session.get(MobileTaskRow, task_id)
        assert task is not None
        session.add(
            MobileTaskEventRow(
                id=str(uuid.uuid4()),
                tenant_id=task.tenant_id,
                task_id=task.id,
                sequence=1,
                event_type="LOG",
                step_index=None,
                step_id=None,
                attempt_id=task.attempt_id,
                payload={"reason": "fixture-before-release"},
                occurred_at=task.started_at,
                received_at=task.started_at,
            )
        )
        task.last_sequence = 1

    released = await client.post(
        f"/companion/v2/tasks/{task_id}/release",
        headers=auth,
        json={"leaseId": old_lease, "reason": "ACCESSIBILITY_NOT_ENABLED"},
    )
    assert released.status_code == 200, released.text
    body = released.json()
    assert body["status"] == "QUEUED"
    assert body["businessState"] == "QUEUED"
    assert body["leaseId"] is None
    assert body["leaseExpiresAt"] is None
    assert body["attempt"] == before["attempt"]
    assert body["deviceIdAtExecution"] == before["deviceIdAtExecution"]
    assert body["lastSequence"] == 1

    async with app.state.database.unit_of_work() as session:
        lease = await session.get(DeviceLeaseRow, device_id)
        task = await session.get(MobileTaskRow, task_id)
        events = list(
            await session.scalars(
                select(MobileTaskEventRow).where(MobileTaskEventRow.task_id == task_id)
            )
        )
        assert lease is not None and lease.lease_id == old_lease
        assert lease.canceled_at is not None
        assert task is not None and task.attempt_id == before["attemptId"]
        assert task.started_at is not None
        assert task.started_at.isoformat() == before["startedAt"].removesuffix("Z")
        assert len(events) == 1

    reclaimed = await client.post(
        "/companion/v2/tasks/claim", headers=auth, json={"leaseSeconds": 60}
    )
    assert reclaimed.status_code == 200, reclaimed.text
    assert reclaimed.json()["taskId"] == task_id
    assert reclaimed.json()["leaseId"] != old_lease
    assert reclaimed.json()["attempt"] == before["attempt"] + 1
    assert reclaimed.json()["attemptId"] == before["attemptId"]
    assert reclaimed.json()["lastSequence"] == 1

    stale = await client.post(
        f"/companion/v2/tasks/{task_id}/release",
        headers=auth,
        json={"leaseId": old_lease, "reason": "ACCESSIBILITY_NOT_ACTIVE"},
    )
    assert stale.status_code == 409


@pytest.mark.asyncio
async def test_companion_release_rejects_wrong_lease_running_and_invalid_body(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, _ = api
    task_id, _, auth, claimed = await _claim_platform_probe(client, "state")
    lease_id = claimed["leaseId"]

    wrong = await client.post(
        f"/companion/v2/tasks/{task_id}/release",
        headers=auth,
        json={"leaseId": str(uuid.uuid4()), "reason": "ACCESSIBILITY_NOT_ACTIVE"},
    )
    assert wrong.status_code == 409
    invalid_reason = await client.post(
        f"/companion/v2/tasks/{task_id}/release",
        headers=auth,
        json={"leaseId": lease_id, "reason": "OTHER"},
    )
    assert invalid_reason.status_code == 422
    extra = await client.post(
        f"/companion/v2/tasks/{task_id}/release",
        headers=auth,
        json={
            "leaseId": lease_id,
            "reason": "ACCESSIBILITY_NOT_ACTIVE",
            "unexpected": True,
        },
    )
    assert extra.status_code == 422

    running = await client.post(
        f"/companion/v2/tasks/{task_id}/heartbeat",
        headers=auth,
        json={"leaseId": lease_id, "currentStep": 0, "leaseSeconds": 60},
    )
    assert running.status_code == 200, running.text
    denied = await client.post(
        f"/companion/v2/tasks/{task_id}/release",
        headers=auth,
        json={"leaseId": lease_id, "reason": "ACCESSIBILITY_NOT_ACTIVE"},
    )
    assert denied.status_code == 409


@pytest.mark.asyncio
@pytest.mark.parametrize("action_status", ["INTENT", "APPLIED", "UNKNOWN", "NOT_SUBMITTED"])
async def test_companion_release_rejects_any_action_commit_row(
    api: tuple[httpx.AsyncClient, FastAPI], action_status: str
) -> None:
    from cloudctl_api.db import MobileActionCommitRow, MobileTaskRow

    client, app = api
    task_id, _, auth, claimed = await _claim_platform_probe(
        client, f"action-{action_status.lower()}"
    )
    async with app.state.database.unit_of_work() as session:
        task = await session.get(MobileTaskRow, task_id)
        assert task is not None
        session.add(
            MobileActionCommitRow(
                action_key=action_status.lower().ljust(64, "0"),
                tenant_id=task.tenant_id,
                task_id=task.id,
                device_id=task.device_id,
                account_id=task.account_id,
                binding_version=task.binding_version,
                recipe_version_id="fixture-recipe",
                recipe_sha256="a" * 64,
                snapshot_sha256="b" * 64,
                action_id="fixture-action",
                parameter_hash="c" * 64,
                lease_id=claimed["leaseId"],
                status=action_status,
                before_evidence="fixture-before",
                reported_evidence=None,
                resolution_revision=0,
                resolution_evidence=None,
                resolved_at=None,
                created_at=task.started_at,
                updated_at=task.started_at,
            )
        )

    denied = await client.post(
        f"/companion/v2/tasks/{task_id}/release",
        headers=auth,
        json={"leaseId": claimed["leaseId"], "reason": "ACCESSIBILITY_NOT_ENABLED"},
    )
    assert denied.status_code == 409


@pytest.mark.asyncio
async def test_companion_release_rejects_legacy_intent_and_mismatched_device_lease(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    from cloudctl_api.db import DeviceLeaseRow, MobileTaskRow

    client, app = api
    task_id, device_id, auth, claimed = await _claim_platform_probe(client, "legacy")
    async with app.state.database.unit_of_work() as session:
        task = await session.get(MobileTaskRow, task_id)
        assert task is not None
        task.command_payload = {**task.command_payload, "commitIntent": False}
    legacy = await client.post(
        f"/companion/v2/tasks/{task_id}/release",
        headers=auth,
        json={"leaseId": claimed["leaseId"], "reason": "ACCESSIBILITY_NOT_ENABLED"},
    )
    assert legacy.status_code == 409

    async with app.state.database.unit_of_work() as session:
        task = await session.get(MobileTaskRow, task_id)
        lease = await session.get(DeviceLeaseRow, device_id)
        assert task is not None and lease is not None
        task.command_payload = {
            key: value for key, value in task.command_payload.items() if key != "commitIntent"
        }
        lease.owner_workflow_id = "auto/not-this-task"
    mismatched = await client.post(
        f"/companion/v2/tasks/{task_id}/release",
        headers=auth,
        json={"leaseId": claimed["leaseId"], "reason": "ACCESSIBILITY_NOT_ACTIVE"},
    )
    assert mismatched.status_code == 409


@pytest.mark.asyncio
async def test_companion_release_requires_unexpired_lease_and_active_binding(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    from datetime import UTC, datetime, timedelta

    from cloudctl_api.db import DeviceLeaseRow, DeviceRow, MobileTaskRow

    client, app = api
    task_id, device_id, auth, claimed = await _claim_platform_probe(client, "expired")
    async with app.state.database.unit_of_work() as session:
        task = await session.get(MobileTaskRow, task_id)
        assert task is not None
        task.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    expired = await client.post(
        f"/companion/v2/tasks/{task_id}/release",
        headers=auth,
        json={"leaseId": claimed["leaseId"], "reason": "ACCESSIBILITY_NOT_ACTIVE"},
    )
    assert expired.status_code == 409

    async with app.state.database.unit_of_work() as session:
        task = await session.get(MobileTaskRow, task_id)
        lease = await session.get(DeviceLeaseRow, device_id)
        assert task is not None and lease is not None
        task.lease_expires_at = datetime.now(UTC) + timedelta(seconds=60)
        lease.canceled_at = datetime.now(UTC)
    canceled = await client.post(
        f"/companion/v2/tasks/{task_id}/release",
        headers=auth,
        json={"leaseId": claimed["leaseId"], "reason": "ACCESSIBILITY_NOT_ACTIVE"},
    )
    assert canceled.status_code == 409

    async with app.state.database.unit_of_work() as session:
        device = await session.get(DeviceRow, device_id)
        lease = await session.get(DeviceLeaseRow, device_id)
        assert device is not None and lease is not None
        lease.canceled_at = None
        device.active_binding_id = str(uuid.uuid4())
    inactive = await client.post(
        f"/companion/v2/tasks/{task_id}/release",
        headers=auth,
        json={"leaseId": claimed["leaseId"], "reason": "ACCESSIBILITY_NOT_ACTIVE"},
    )
    assert inactive.status_code in {401, 403}


@pytest.mark.asyncio
async def test_platform_claim_returns_command_v1_without_legacy_steps(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    from cloudctl_api.builtin_recipes import builtin_recipe_ref
    from cloudctl_api.command_v1 import parse_command_v1

    client, _ = api
    device_id = await create_direct_device(client, "phone-command-v1")
    account = await create_account(client, "xy-command-v1")
    bound = await bind(client, account, device_id)
    created = await client.post(
        "/api/v1/platform-tasks",
        headers={**identity(), "Idempotency-Key": "command-v1-claim"},
        json={
            "deviceId": device_id,
            "accountId": account,
            "expectedBindingVersion": bound["bindingVersion"],
            **PROBE,
        },
    )
    assert created.status_code == 201, created.text
    task_id = created.json()["items"][0]["taskId"]
    auth = await _enroll(client, device_id, "instance-command-v1")
    claimed = await client.post("/companion/v2/tasks/claim", headers=auth, json={"leaseSeconds": 60})
    assert claimed.status_code == 200, claimed.text
    body = claimed.json()
    assert body["protocolVersion"] == "cloudctl.command/v1"
    assert "steps" not in body
    command = parse_command_v1(body["command"])
    assert command["taskId"] == task_id
    assert command["commandType"] == "device.probe_capabilities.v1"
    assert command["deviceId"] == device_id
    assert command["accountId"] == account
    assert command["bindingVersion"] == bound["bindingVersion"]
    assert command["recipe"] == builtin_recipe_ref("device.probe_capabilities.v1")
    assert command["legacyStepsEnabled"] is False
    assert command["lease"]["controlEpoch"] >= 1


@pytest.mark.asyncio
async def test_platform_publish_claim_is_open_only_command_v1(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    from cloudctl_api.builtin_recipes import OPEN_ONLY_COMMAND_TYPES, builtin_recipe_ref
    from cloudctl_api.command_v1 import parse_command_v1

    client, _ = api
    device_id = await create_direct_device(client, "phone-command-publish")
    account = await create_account(client, "xy-command-publish")
    bound = await bind(client, account, device_id)
    created = await client.post(
        "/api/v1/platform-tasks",
        headers={**identity(), "Idempotency-Key": "command-v1-publish"},
        json={
            "deviceId": device_id,
            "accountId": account,
            "expectedBindingVersion": bound["bindingVersion"],
            "commandType": "xianyu.publish_listing.v1",
            "parameters": {
                "listingBody": "自用闲置，功能正常，支持当面交易",
                "price": "128",
            },
        },
    )
    assert created.status_code == 201, created.text
    auth = await _enroll(client, device_id, "instance-command-publish")
    claimed = await client.post("/companion/v2/tasks/claim", headers=auth, json={"leaseSeconds": 60})
    assert claimed.status_code == 200, claimed.text
    command = parse_command_v1(claimed.json()["command"])
    assert command["commandType"] in OPEN_ONLY_COMMAND_TYPES
    assert command["targetPackage"] == "com.taobao.idlefish"
    assert command["recipe"] == builtin_recipe_ref("xianyu.publish_listing.v1")
    assert command["legacyStepsEnabled"] is False
    assert "steps" not in claimed.json()


@pytest.mark.asyncio
async def test_operation_id_mints_command_v1_and_rejects_unwired_catalog(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    from cloudctl_api.command_v1 import parse_command_v1

    client, _ = api
    device_id = await create_direct_device(client, "phone-factory")
    account = await create_account(client, "xy-factory")
    bound = await bind(client, account, device_id)
    denied = await client.post(
        "/api/v1/platform-tasks",
        headers={**identity(), "Idempotency-Key": "factory-polish"},
        json={
            "deviceId": device_id,
            "accountId": account,
            "expectedBindingVersion": bound["bindingVersion"],
            "operationId": "xy-tasks-03",
            "parameters": {"intervalSeconds": 15},
        },
    )
    assert denied.status_code == 422
    created = await client.post(
        "/api/v1/platform-tasks",
        headers={**identity(), "Idempotency-Key": "factory-probe"},
        json={
            "deviceId": device_id,
            "accountId": account,
            "expectedBindingVersion": bound["bindingVersion"],
            "operationId": "device-probe",
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["items"][0]["commandType"] == "device.probe_capabilities.v1"
    auth = await _enroll(client, device_id, "instance-factory")
    claimed = await client.post("/companion/v2/tasks/claim", headers=auth, json={"leaseSeconds": 60})
    assert claimed.status_code == 200, claimed.text
    command = parse_command_v1(claimed.json()["command"])
    assert command["commandType"] == "device.probe_capabilities.v1"
    assert command["legacyStepsEnabled"] is False
