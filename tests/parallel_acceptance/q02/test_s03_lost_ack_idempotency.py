"""Q02 scenario 3 (class A): lost ACKs and duplicate reports stay idempotent.

A companion report can be lost or duplicated (network replay). Acceptance:
replayed task creation with the same Idempotency-Key never mints a second
task; replayed events with identical content are absorbed (sequence stays
monotonic, no duplicates); a lost ACK followed by re-claim increments the
attempt on the same task instead of creating a parallel runner; replayed
completion is absorbed while a divergent completion is refused.
"""

from __future__ import annotations

import uuid

import httpx
from cloudctl_api.db import DeviceLeaseRow, MobileTaskEventRow, MobileTaskRow
from fastapi import FastAPI
from sqlalchemy import select

from .conftest import bind, create_account, create_direct_device, enroll, identity
from .harness import claim, expire_lease, post_event, running_steps_task

PROBE = {
    "commandType": "device.probe_capabilities.v1",
    "parameters": {},
}


async def test_s03a_task_creation_replay_never_duplicates(
    api: tuple[httpx.AsyncClient, FastAPI], ledger
) -> None:
    client, app = api
    device_id = await create_direct_device(client, "phone-s03a")
    account = await create_account(client, "xy-s03a")
    await bind(client, account, device_id)
    key = f"q02-replay-{uuid.uuid4().hex[:12]}"
    payload = {"deviceId": device_id, "accountId": account, **PROBE}

    first = await client.post(
        "/api/v1/platform-tasks", headers={**identity(), "Idempotency-Key": key}, json=payload
    )
    assert first.status_code == 201, first.text
    replay = await client.post(
        "/api/v1/platform-tasks", headers={**identity(), "Idempotency-Key": key}, json=payload
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["items"][0]["taskId"] == first.json()["items"][0]["taskId"]
    ledger.record(
        "creation-replay-idempotent", taskId=first.json()["items"][0]["taskId"], idempotencyKey=key
    )

    async with app.state.database.unit_of_work() as session:
        rows = list(
            await session.scalars(
                select(MobileTaskRow).where(MobileTaskRow.device_id == device_id)
            )
        )
        assert len(rows) == 1, "duplicate creation must not mint a second task"


async def test_s03b_lost_and_duplicated_events_absorbed_monotonic(
    api: tuple[httpx.AsyncClient, FastAPI], ledger
) -> None:
    client, app = api
    ctx = await running_steps_task(api)

    first = await post_event(client, ctx, 1, "LOG", {"stepId": "fill-description"})
    assert first.status_code == 201, first.text
    second = await post_event(client, ctx, 2, "LOG", {"stepId": "click-publish"})
    assert second.status_code == 201, second.text

    lost_ack_replay = await post_event(client, ctx, 2, "LOG", {"stepId": "click-publish"})
    assert lost_ack_replay.status_code == 200, lost_ack_replay.text
    assert lost_ack_replay.headers["Idempotency-Replayed"] == "true"
    older_replay = await post_event(client, ctx, 1, "LOG", {"stepId": "fill-description"})
    assert older_replay.status_code == 200, older_replay.text

    third = await post_event(client, ctx, 3, "LOG", {"stepId": "wait-publish-complete"})
    assert third.status_code == 201, third.text

    async with app.state.database.unit_of_work() as session:
        events = list(
            await session.scalars(
                select(MobileTaskEventRow)
                .where(MobileTaskEventRow.task_id == ctx["taskId"])
                .order_by(MobileTaskEventRow.sequence)
            )
        )
        assert [event.sequence for event in events] == [1, 2, 3]
        task = await session.get(MobileTaskRow, ctx["taskId"])
        assert task is not None
        assert task.last_sequence == 3
    ledger.record("event-replay-absorbed", taskId=ctx["taskId"], sequences=[1, 2, 3])


async def test_s03c_lost_claim_ack_reclaim_same_task_attempt_increment(
    api: tuple[httpx.AsyncClient, FastAPI], ledger
) -> None:
    client, app = api
    ctx = await running_steps_task(api)
    task_id = ctx["taskId"]
    first_lease = ctx["leaseId"]
    first_attempt = ctx["claimed"]["attempt"]

    async with app.state.database.unit_of_work() as session:
        lease_before = await session.get(DeviceLeaseRow, ctx["deviceId"])
        assert lease_before is not None
        token_before = lease_before.fencing_token
        row_before = await session.get(MobileTaskRow, task_id)
        assert row_before is not None
        attempt_id_before = row_before.attempt_id

    await expire_lease(app, task_id)
    reclaimed = await claim(client, ctx["auth"])
    assert reclaimed["taskId"] == task_id, "lost ACK must resume the same task, not mint a new one"
    assert reclaimed["attempt"] == first_attempt + 1

    async with app.state.database.unit_of_work() as session:
        lease_after = await session.get(DeviceLeaseRow, ctx["deviceId"])
        assert lease_after is not None
        assert lease_after.lease_id == reclaimed["leaseId"]
        assert lease_after.fencing_token > token_before, (
            "re-claim must mint a strictly higher fencing token"
        )
        row_after = await session.get(MobileTaskRow, task_id)
        assert row_after is not None
        assert row_after.attempt_id == attempt_id_before
        rows = list(
            await session.scalars(
                select(MobileTaskRow).where(MobileTaskRow.device_id == ctx["deviceId"])
            )
        )
        assert len(rows) == 1
    ledger.record(
        "reclaim-same-task",
        taskId=task_id,
        attemptBefore=first_attempt,
        attemptAfter=reclaimed["attempt"],
        attemptId=attempt_id_before,
        oldLease=first_lease,
        newLease=reclaimed["leaseId"],
    )


async def test_s03d_completion_replay_absorbed_divergence_refused(
    api: tuple[httpx.AsyncClient, FastAPI], ledger
) -> None:
    """Completion replay on a typed command (probe): wrong type refused,
    identical replay absorbed, divergent second completion refused."""
    client, _ = api
    device_id = await create_direct_device(client, "phone-s03d")
    account = await create_account(client, "xy-s03d")
    await bind(client, account, device_id)
    created = await client.post(
        "/api/v1/platform-tasks",
        headers={**identity(), "Idempotency-Key": f"s03d-{uuid.uuid4().hex[:12]}"},
        json={"deviceId": device_id, "accountId": account, **PROBE},
    )
    assert created.status_code == 201, created.text
    task_id = created.json()["items"][0]["taskId"]
    auth = await enroll(client, device_id, "instance-s03d")
    claimed = await claim(client, auth)
    assert claimed["taskId"] == task_id
    started = await client.post(
        f"/companion/v2/tasks/{task_id}/heartbeat",
        headers=auth,
        json={"leaseId": claimed["leaseId"], "currentStep": 0, "leaseSeconds": 60},
    )
    assert started.status_code == 200, started.text

    completion = {
        "leaseId": claimed["leaseId"],
        "result": {"outcome": "ok", "resultType": "DeviceProbeResult", "schemaVersion": 1},
    }
    wrong_type = {
        "leaseId": claimed["leaseId"],
        "result": {
            "outcome": "ok",
            "resultType": "XianyuPublishListingResult",
            "schemaVersion": 1,
        },
    }
    assert (
        await client.post(
            f"/companion/v2/tasks/{task_id}/complete", headers=auth, json=wrong_type
        )
    ).status_code == 422

    first = await client.post(
        f"/companion/v2/tasks/{task_id}/complete", headers=auth, json=completion
    )
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "SUCCEEDED"
    duplicate = await client.post(
        f"/companion/v2/tasks/{task_id}/complete", headers=auth, json=completion
    )
    assert duplicate.status_code == 200, duplicate.text
    assert duplicate.json()["status"] == "SUCCEEDED"

    divergent = await client.post(
        f"/companion/v2/tasks/{task_id}/complete",
        headers=auth,
        json={"leaseId": claimed["leaseId"], "result": {"outcome": "different"}},
    )
    assert divergent.status_code == 409, divergent.text
    ledger.record("completion-replay", taskId=task_id, terminal="SUCCEEDED")
