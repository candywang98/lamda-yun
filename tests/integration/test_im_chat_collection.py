"""No-send snapshot protocol: ownership, old-client gates and terminal fencing."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest
from cloudctl_api.db import DeviceLeaseRow, DeviceRow, MobileTaskRow
from test_im_aggregation import _push
from test_p14_recipe_versions import api, isolated_postgres, pg_url  # noqa: F401
from test_platform_tasks import _enroll, create_direct_device, identity

PROTOCOL = "im-chat-collection/1"


async def heartbeat(client, auth, *, supported=True):
    payload = {
        "companionVersion": "collection-test",
        "accessibilityEnabled": True,
        "runnerState": "IDLE",
    }
    if supported:
        payload["imChatCollectionProtocol"] = PROTOCOL
    response = await client.post("/companion/v2/devices/heartbeat", headers=auth, json=payload)
    assert response.status_code == 200, response.text


async def setup(client, *, supported=True):
    device = await create_direct_device(client, "im-body")
    auth = await _enroll(client, device, "body-instance")
    await heartbeat(client, auth, supported=supported)
    await _push(client, auth, peer="buyer-body")
    threads = (await client.get("/api/v1/im/threads", headers=identity())).json()["items"]
    thread = next(t for t in threads if t["deviceId"] == device)
    return device, auth, thread["id"]


async def create(client, thread, key="body-key"):
    return await client.post(
        f"/api/v1/im/threads/{thread}:collect-body",
        headers={**identity(), "Idempotency-Key": key},
        json={},
    )


async def claim(client, auth, *, supported=True):
    body = {"leaseSeconds": 60}
    if supported:
        body["imChatCollectionProtocol"] = PROTOCOL
    return await client.post("/companion/v2/tasks/claim", headers=auth, json=body)


def completion(task):
    return {
        "leaseId": task["leaseId"],
        "controlEpoch": task["controlEpoch"],
        "protocolVersion": PROTOCOL,
        "target": task["steps"][0]["target"],
        "snapshot": {
            "capturedAt": datetime.now(UTC).isoformat(),
            "scope": "VISIBLE_SCREEN",
            "completeness": "VISIBLE_ONLY",
            "accountIdentity": "UNVERIFIED",
            "peerIdentity": {
                "status": "DISPLAY_NAME_MATCH",
                "basis": "CHAT_HEADER",
                "observedName": "buyer-body",
            },
            "messages": [
                {"direction": "IN", "text": "visible body", "visibleOrder": 0, "occurredAt": None},
                {
                    "direction": "OUT",
                    "text": "my historical reply",
                    "visibleOrder": 1,
                    "occurredAt": None,
                },
            ],
            "truncated": False,
        },
    }


async def post_complete(client, auth, task, body):
    return await client.post(
        f"/companion/v2/im/chat-collections/{task['id']}:complete", headers=auth, json=body
    )


async def test_roundtrip_idempotency_and_notification_isolation(api):  # noqa: F811
    client, app = api
    _, auth, thread = await setup(client)
    app.state.im_service.receive_only = True
    first = await create(client, thread)
    assert first.status_code == 201, first.text
    replay = await create(client, thread)
    assert replay.status_code == 200 and replay.json() == first.json()
    assert (
        await client.post(
            f"/api/v1/im/threads/{thread}:reply", headers=identity(), json={"text": "never sent"}
        )
    ).status_code == 409
    assert (await claim(client, auth, supported=False)).status_code == 204
    claimed = await claim(client, auth)
    assert claimed.status_code == 200, claimed.text
    task = claimed.json()
    body = completion(task)
    generic = await client.post(
        f"/companion/v2/tasks/{task['id']}/complete",
        headers=auth,
        json={"leaseId": task["leaseId"], "result": {}},
    )
    assert generic.status_code == 409
    finished = await post_complete(client, auth, task, body)
    assert finished.status_code == 200, finished.text
    assert (await post_complete(client, auth, task, body)).json() == finished.json()
    changed = deepcopy(body)
    changed["snapshot"]["truncated"] = True
    assert (await post_complete(client, auth, task, changed)).status_code == 409
    failed = await client.post(
        f"/companion/v2/tasks/{task['id']}/fail",
        headers=auth,
        json={"leaseId": task["leaseId"], "errorCode": "LATE_FAILURE", "detail": "late failure"},
    )
    assert failed.status_code == 409, failed.text
    history = (
        await client.get(f"/api/v1/im/threads/{thread}/body-collections", headers=identity())
    ).json()
    assert history["capability"] == {"supported": True, "available": True, "reason": None}
    assert history["items"][0]["snapshot"]["messages"] == body["snapshot"]["messages"]
    messages = (
        await client.get(f"/api/v1/im/threads/{thread}/messages", headers=identity())
    ).json()["items"]
    assert len(messages) == 1 and messages[0]["direction"] == "IN"


async def test_capability_removal_creation_and_claim_gate(api):  # noqa: F811
    client, _ = api
    _, auth, thread = await setup(client, supported=False)
    assert (await create(client, thread)).status_code == 409
    await heartbeat(client, auth)
    assert (await create(client, thread)).status_code == 201
    await heartbeat(client, auth, supported=False)
    assert (await claim(client, auth)).status_code == 204
    view = (
        await client.get(f"/api/v1/im/threads/{thread}/body-collections", headers=identity())
    ).json()
    assert view["capability"]["supported"] is False
    await heartbeat(client, auth)
    assert (await claim(client, auth)).status_code == 200


@pytest.mark.parametrize(
    "field", ["tenantId", "deviceId", "threadId", "peerKey", "peerName", "mobileBindingId"]
)
async def test_generic_create_rejects_forged_target(api, field):  # noqa: F811
    client, _ = api
    _, auth, thread = await setup(client)
    assert (await create(client, thread)).status_code == 201
    task = (await claim(client, auth)).json()
    step = deepcopy(task["steps"][0])
    step["target"][field] = (
        "wrong" if field.startswith("peer") else "00000000-0000-4000-8000-000000000099"
    )
    result = await client.post(
        "/api/v1/mobile/tasks",
        headers={**identity(), "Idempotency-Key": "forge"},
        json={
            "deviceId": task["deviceId"],
            "targetPackage": task["targetPackage"],
            "totalTimeoutMs": 60000,
            "steps": [step],
        },
    )
    assert result.status_code == 409, result.text


async def test_mixed_steps_and_create_body_overrides_rejected(api):  # noqa: F811
    client, _ = api
    _, auth, thread = await setup(client)
    assert (
        await client.post(
            f"/api/v1/im/threads/{thread}:collect-body",
            headers={**identity(), "Idempotency-Key": "override"},
            json={"peerName": "other"},
        )
    ).status_code == 422
    assert (await create(client, thread)).status_code == 201
    task = (await claim(client, auth)).json()
    result = await client.post(
        "/api/v1/mobile/tasks",
        headers={**identity(), "Idempotency-Key": "mixed"},
        json={
            "deviceId": task["deviceId"],
            "targetPackage": task["targetPackage"],
            "totalTimeoutMs": 61000,
            "steps": [
                *task["steps"],
                {
                    "stepId": "send",
                    "action": "ui.tap",
                    "timeoutMs": 1000,
                    "locatorRef": "xianyu_chat_send",
                },
            ],
        },
    )
    assert result.status_code == 422


@pytest.mark.parametrize(
    "damage",
    ["lease", "fence", "expired", "device_lease", "binding", "peer", "target", "immutable"],
)
async def test_completion_rejects_stale_or_wrong_authority(api, damage):  # noqa: F811
    client, app = api
    device, auth, thread = await setup(client)
    assert (await create(client, thread)).status_code == 201
    task = (await claim(client, auth)).json()
    body = completion(task)
    if damage == "lease":
        body["leaseId"] = "wrong"
    elif damage == "fence":
        body["controlEpoch"] += 1
    elif damage == "peer":
        body["snapshot"]["peerIdentity"]["observedName"] = "other"
    elif damage == "target":
        body["target"]["peerKey"] = "other"
    else:
        async with app.state.database.unit_of_work() as session:
            row = await session.get(MobileTaskRow, task["id"])
            if damage == "expired":
                row.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
            elif damage == "device_lease":
                lease = await session.get(DeviceLeaseRow, device)
                lease.canceled_at = datetime.now(UTC)
            elif damage == "binding":
                dev = await session.get(DeviceRow, device)
                dev.active_binding_id = None
            else:
                steps = deepcopy(row.steps)
                steps[1]["target"]["peerKey"] = "mutated"
                row.steps = steps
    result = await post_complete(client, auth, task, body)
    assert result.status_code in (401, 409), result.text
    async with app.state.database.unit_of_work() as session:
        row = await session.get(MobileTaskRow, task["id"])
        assert row.result == {} and row.status != "SUCCEEDED"


@pytest.mark.parametrize(
    "damage",
    [
        "direction",
        "order",
        "timestamp",
        "extra",
        "account",
        "size",
        "count",
        "no_offset",
        "non_utc",
        "blank",
    ],
)
async def test_snapshot_validation(api, damage):  # noqa: F811
    client, _ = api
    _, auth, thread = await setup(client)
    await create(client, thread)
    task = (await claim(client, auth)).json()
    body = completion(task)
    snapshot = body["snapshot"]
    if damage == "direction":
        snapshot["messages"][0]["direction"] = "SYSTEM"
    elif damage == "order":
        snapshot["messages"][1]["visibleOrder"] = 0
    elif damage == "timestamp":
        snapshot["messages"][0]["occurredAt"] = datetime.now(UTC).isoformat()
    elif damage == "extra":
        snapshot["verified"] = True
    elif damage == "account":
        snapshot["accountIdentity"] = "VERIFIED"
    elif damage == "size":
        snapshot["messages"] = [
            {"direction": "IN", "text": "汉" * 2000, "visibleOrder": i, "occurredAt": None}
            for i in range(20)
        ]
    elif damage == "count":
        snapshot["messages"] *= 11
    elif damage == "no_offset":
        snapshot["capturedAt"] = "2026-10-11T12:00:00"
    elif damage == "non_utc":
        snapshot["capturedAt"] = "2026-10-11T12:00:00+08:00"
    else:
        snapshot["messages"][0]["text"] = " "
    result = await post_complete(client, auth, task, body)
    assert result.status_code == 422, result.text


async def test_empty_snapshot_and_transport_bound(api):  # noqa: F811
    client, _ = api
    _, auth, thread = await setup(client)
    await create(client, thread)
    task = (await claim(client, auth)).json()
    large = await client.post(
        f"/companion/v2/im/chat-collections/{task['id']}:complete",
        headers={**auth, "Content-Type": "application/json"},
        content=b" " * 400001,
    )
    assert large.status_code == 413
    body = completion(task)
    body["snapshot"]["messages"] = []
    assert (await post_complete(client, auth, task, body)).status_code == 200


async def test_concurrent_idempotency_on_postgres(api):  # noqa: F811
    client, app = api
    if app.state.database.engine.dialect.name != "postgresql":
        pytest.skip("concurrency requires row-locking database")
    _, _, thread = await setup(client)
    responses = await asyncio.gather(create(client, thread), create(client, thread))
    assert sorted(response.status_code for response in responses) == [200, 201]
    assert responses[0].json() == responses[1].json()


async def test_idempotency_target_conflict_and_cross_tenant_query(api):  # noqa: F811
    client, _ = api
    _, auth, thread = await setup(client)
    assert (await create(client, thread)).status_code == 201
    await _push(client, auth, peer="second-peer")
    threads = (await client.get("/api/v1/im/threads", headers=identity())).json()["items"]
    other = next(item["id"] for item in threads if item["peerKey"] == "second-peer")
    assert (await create(client, other)).status_code == 409
    foreign = {**identity(), "X-Tenant-Id": "00000000-0000-4000-8000-000000000099"}
    assert (
        await client.get(f"/api/v1/im/threads/{thread}/body-collections", headers=foreign)
    ).status_code == 404
    assert (
        await client.post(
            f"/api/v1/im/threads/{thread}:collect-body",
            headers={**foreign, "Idempotency-Key": "other"},
            json={},
        )
    ).status_code == 404


async def test_rebind_invalidates_capability_and_queued_target(api):  # noqa: F811
    client, _ = api
    device, auth, thread = await setup(client)
    await create(client, thread)
    replacement = await _enroll(client, device, "replacement-instance")
    view = (
        await client.get(f"/api/v1/im/threads/{thread}/body-collections", headers=identity())
    ).json()
    assert not view["capability"]["supported"]
    await heartbeat(client, replacement)
    assert (await claim(client, replacement)).status_code == 204
    view = (
        await client.get(f"/api/v1/im/threads/{thread}/body-collections", headers=identity())
    ).json()
    assert view["items"][0]["status"] == "FAILED"
    assert (await claim(client, auth)).status_code == 401


async def test_new_lease_cannot_replay_old_completion(api):  # noqa: F811
    client, app = api
    device, auth, thread = await setup(client)
    await create(client, thread)
    original = (await claim(client, auth)).json()
    old_body = completion(original)
    async with app.state.database.unit_of_work() as session:
        task = await session.get(MobileTaskRow, original["id"])
        task.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
        lease = await session.get(DeviceLeaseRow, device)
        lease.expires_at = task.lease_expires_at
    replacement = (await claim(client, auth)).json()
    assert replacement["controlEpoch"] > original["controlEpoch"]
    assert (await post_complete(client, auth, original, old_body)).status_code == 409
    assert (
        await post_complete(client, auth, replacement, completion(replacement))
    ).status_code == 200


async def test_concurrent_completion_is_atomic_on_postgres(api):  # noqa: F811
    client, app = api
    if app.state.database.engine.dialect.name != "postgresql":
        pytest.skip("concurrency requires row-locking database")
    _, auth, thread = await setup(client)
    await create(client, thread)
    task = (await claim(client, auth)).json()
    body = completion(task)
    replies = await asyncio.gather(
        post_complete(client, auth, task, body), post_complete(client, auth, task, body)
    )
    assert [reply.status_code for reply in replies] == [200, 200]
    assert replies[0].json() == replies[1].json()


async def test_wrong_device_and_failed_task_cannot_store_snapshot(api):  # noqa: F811
    client, app = api
    _, auth, thread = await setup(client)
    await create(client, thread)
    task = (await claim(client, auth)).json()
    second = await create_direct_device(client, "other-device")
    second_auth = await _enroll(client, second, "other-instance")
    body = completion(task)
    assert (await post_complete(client, second_auth, task, body)).status_code == 404
    failed = await client.post(
        f"/companion/v2/tasks/{task['id']}/fail",
        headers=auth,
        json={
            "leaseId": task["leaseId"],
            "errorCode": "IDENTITY_DRIFT",
            "detail": "Chat header changed",
        },
    )
    assert failed.status_code == 200, failed.text
    assert (await post_complete(client, auth, task, body)).status_code == 409
    async with app.state.database.unit_of_work() as session:
        row = await session.get(MobileTaskRow, task["id"])
        assert row.result == {} and row.business_state == "FAILED"


async def test_capability_offline_and_permission_gate(api):  # noqa: F811
    client, app = api
    device, _, thread = await setup(client)
    forbidden = await client.post(
        f"/api/v1/im/threads/{thread}:collect-body",
        headers={**identity(role="viewer"), "Idempotency-Key": "viewer"},
        json={},
    )
    assert forbidden.status_code == 403
    async with app.state.database.unit_of_work() as session:
        row = await session.get(DeviceRow, device)
        row.last_seen_at = datetime.now(UTC) - timedelta(hours=1)
    view = (
        await client.get(f"/api/v1/im/threads/{thread}/body-collections", headers=identity())
    ).json()["capability"]
    assert view == {"supported": True, "available": False, "reason": "IM_COLLECTION_OFFLINE"}
    assert (await create(client, thread)).status_code == 409
