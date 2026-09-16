"""Q02 scenario 5 (class A): stale leases and fencing tokens.

Every device command carries a lease ID and a monotonically increasing
fencing token (repo invariant 3). After control_epoch advances (resume or
re-claim), commands signed with the old lease/epoch must be refused across
every companion channel: heartbeat, events, ledger intent, outcome,
completion, and release.
"""

from __future__ import annotations

import uuid

import httpx
from cloudctl_api.db import DeviceLeaseRow, MobileActionCommitRow, MobileTaskRow
from fastapi import FastAPI
from sqlalchemy import select

from .conftest import identity
from .harness import (
    action_paths,
    claim,
    device_counters,
    expire_lease,
    intent_body,
    post_event,
    running_steps_task,
)
from .mock_platform import PostconditionReadbackStub


async def test_s05a_epoch_bump_invalidates_old_lease_on_all_channels(
    api: tuple[httpx.AsyncClient, FastAPI], ledger
) -> None:
    client, app = api
    ctx = await running_steps_task(api)
    task_id = ctx["taskId"]
    old_lease = ctx["leaseId"]
    fencing_before, epoch_before = await device_counters(app, ctx["deviceId"])

    paused = await client.post(
        f"/api/v1/platform-tasks/{task_id}:pause",
        headers=identity(),
        json={"reason": "operator taking over"},
    )
    assert paused.status_code == 200, paused.text
    acked = await client.post(
        f"/api/v1/platform-tasks/{task_id}:ack-paused",
        headers=identity(),
        json={"leaseId": old_lease},
    )
    assert acked.status_code == 200, acked.text
    assert acked.json()["state"] == "PAUSED_WAITING_USER"

    resumed = await client.post(
        f"/api/v1/platform-tasks/{task_id}:resume",
        headers=identity(),
        json={"reason": "operator returned to the frozen page", "pageVerified": True},
    )
    assert resumed.status_code == 200, resumed.text
    assert resumed.json()["controlEpoch"], "resume must surface the new control epoch"
    fencing_after, epoch_after = await device_counters(app, ctx["deviceId"])
    assert fencing_after == fencing_before + 1
    assert epoch_after == epoch_before + 1

    async with app.state.database.unit_of_work() as session:
        row = await session.get(MobileTaskRow, task_id)
        assert row is not None
        assert row.lease_id != old_lease
        live_lease = row.lease_id
        lease_row = await session.get(DeviceLeaseRow, ctx["deviceId"])
        assert lease_row is not None
        assert lease_row.lease_id == live_lease
        assert lease_row.fencing_token == fencing_after

    stale_heartbeat = await client.post(
        f"/companion/v2/tasks/{task_id}/heartbeat",
        headers=ctx["auth"],
        json={"leaseId": old_lease, "currentStep": 2, "leaseSeconds": 60},
    )
    assert stale_heartbeat.status_code == 409, stale_heartbeat.text

    stale_event = await post_event(
        client, ctx, 1, "LOG", {"stepId": "fill-description"}, lease_id=old_lease
    )
    assert stale_event.status_code == 409, stale_event.text

    stale_intent = await client.post(
        f"/companion/v2/tasks/{task_id}/actions/intent",
        headers=ctx["auth"],
        json=intent_body(ctx, before_evidence="evidence://before"),
    )
    assert stale_intent.status_code == 409, stale_intent.text

    live_heartbeat = await client.post(
        f"/companion/v2/tasks/{task_id}/heartbeat",
        headers=ctx["auth"],
        json={"leaseId": live_lease, "currentStep": 2, "leaseSeconds": 60},
    )
    assert live_heartbeat.status_code == 200, live_heartbeat.text
    assert live_heartbeat.json()["businessState"] == "RUNNING"

    stale_completion = await client.post(
        f"/companion/v2/tasks/{task_id}/complete",
        headers=ctx["auth"],
        json={"leaseId": old_lease, "result": {"outcome": "ok"}},
    )
    assert stale_completion.status_code == 409, stale_completion.text
    ledger.record(
        "stale-lease-refused",
        taskId=task_id,
        oldLease=old_lease,
        newLease=live_lease,
        fencingBefore=fencing_before,
        fencingAfter=fencing_after,
        epochBefore=epoch_before,
        epochAfter=epoch_after,
    )


async def test_s05b_reclaim_mints_higher_token_old_release_refused(
    api: tuple[httpx.AsyncClient, FastAPI], ledger
) -> None:
    client, app = api
    ctx = await running_steps_task(api, with_heartbeat=False)
    task_id = ctx["taskId"]
    old_lease = ctx["leaseId"]

    async with app.state.database.unit_of_work() as session:
        lease_before = await session.get(DeviceLeaseRow, ctx["deviceId"])
        assert lease_before is not None
        assert lease_before.fencing_token == ctx["claimed"]["controlEpoch"]

    await expire_lease(app, task_id)
    reclaimed = await claim(client, ctx["auth"])
    assert reclaimed["taskId"] == task_id
    assert reclaimed["leaseId"] != old_lease

    stale_release = await client.post(
        f"/companion/v2/tasks/{task_id}/release",
        headers=ctx["auth"],
        json={"leaseId": old_lease, "reason": "ACCESSIBILITY_NOT_ENABLED"},
    )
    assert stale_release.status_code == 409, stale_release.text
    ledger.record(
        "reclaim-fencing",
        taskId=task_id,
        oldLease=old_lease,
        newLease=reclaimed["leaseId"],
        tokenBefore=lease_before.fencing_token,
    )


async def test_s05c_stale_lease_cannot_report_outcome(
    api: tuple[httpx.AsyncClient, FastAPI], ledger
) -> None:
    """An authorized intent is not writable by a lease that was replaced."""
    client, app = api
    ctx = await running_steps_task(api)
    readback = PostconditionReadbackStub(postcondition_present=True)
    body = intent_body(ctx, before_evidence=readback.before_evidence())
    intent, action = action_paths(ctx)
    assert (await client.post(intent, headers=ctx["auth"], json=body)).status_code == 201

    forged = {
        "leaseId": str(uuid.uuid4()),
        "parameterHash": body["parameterHash"],
        "status": "APPLIED",
        "evidence": readback.verdict()[1],
    }
    response = await client.post(action + "/outcome", headers=ctx["auth"], json=forged)
    assert response.status_code == 409, response.text

    async with app.state.database.unit_of_work() as session:
        rows = list(
            await session.scalars(
                select(MobileActionCommitRow).where(
                    MobileActionCommitRow.task_id == ctx["taskId"]
                )
            )
        )
        assert len(rows) == 1
        assert rows[0].status == "INTENT", "stale lease must not resolve the action"
    ledger.record("stale-outcome-refused", taskId=ctx["taskId"], actionKey=body["actionKey"])
