"""Q02 scenario 7 (class A): same-task recovery (pause -> ack -> resume -> continue).

Acceptance: the original task keeps its taskId, attemptId, frozen parameters,
snapshot hash, and recipe pin across the pause/resume cycle and across a lost
lease re-claim (attempt increments on the same task); control_epoch advances
and the resumed runner continues under a fresh lease into RESUME_CHECK and
back to RUNNING before completion.
"""

from __future__ import annotations

import httpx
from cloudctl_api.db import MobileTaskRow
from fastapi import FastAPI

from .conftest import identity
from .harness import claim, device_counters, expire_lease, post_event, running_steps_task


def _frozen_task_view(row: MobileTaskRow) -> dict:
    # controlEpoch is a dynamic header stamped by claim/resume (fencing); the
    # frozen comparison strips it so only real step parameters are compared.
    steps = [
        {key: value for key, value in step.items() if key != "controlEpoch"}
        for step in (row.steps or [])
        if step.get("action")
    ]
    return {
        "parameters": (row.command_payload or {}).get("parameters"),
        "snapshot": (row.command_payload or {}).get("snapshotSha256"),
        "pin": row.recipe_pin,
        "steps": steps,
    }


async def _load_task(app: FastAPI, task_id: str) -> MobileTaskRow:
    async with app.state.database.unit_of_work() as session:
        row = await session.get(MobileTaskRow, task_id)
        assert row is not None
        return row


async def test_s07a_pause_ack_resume_check_continue_same_task(
    api: tuple[httpx.AsyncClient, FastAPI], ledger
) -> None:
    client, app = api
    ctx = await running_steps_task(api)
    task_id = ctx["taskId"]
    before = await _load_task(app, task_id)
    frozen_before = _frozen_task_view(before)
    fencing_before, epoch_before = await device_counters(app, ctx["deviceId"])

    paused = await client.post(
        f"/api/v1/platform-tasks/{task_id}:pause",
        headers=identity(),
        json={"reason": "operator taking over"},
    )
    assert paused.status_code == 200, paused.text
    assert paused.json()["state"] == "PAUSE_REQUESTED"

    ack = await post_event(
        client, ctx, 1, "PAUSED_WAITING_USER", {"reason": "operator taking over"}
    )
    assert ack.status_code == 201, ack.text
    detail = await client.get(f"/api/v1/platform-tasks/{task_id}", headers=identity())
    assert detail.json()["state"] == "PAUSED_WAITING_USER"
    assert detail.json()["controlMode"] == "REMOTE"

    denied = await client.post(
        f"/api/v1/platform-tasks/{task_id}:resume",
        headers=identity(),
        json={"reason": "page not verified", "pageVerified": False},
    )
    assert denied.status_code == 422, denied.text
    still_paused = await client.get(f"/api/v1/platform-tasks/{task_id}", headers=identity())
    assert still_paused.json()["state"] == "PAUSED_WAITING_USER"

    resumed = await client.post(
        f"/api/v1/platform-tasks/{task_id}:resume",
        headers=identity(),
        json={"reason": "operator returned to the frozen page", "pageVerified": True},
    )
    assert resumed.status_code == 200, resumed.text
    assert resumed.json()["taskId"] == task_id
    assert resumed.json()["state"] == "RESUME_CHECK"
    assert resumed.json()["resumeCount"] == 1
    assert resumed.json()["controlMode"] == "AUTO"
    fencing_after, epoch_after = await device_counters(app, ctx["deviceId"])
    assert fencing_after == fencing_before + 1
    assert epoch_after == epoch_before + 1

    async with app.state.database.unit_of_work() as session:
        row = await session.get(MobileTaskRow, task_id)
        assert row is not None
        new_lease = row.lease_id
        assert new_lease is not None
        assert new_lease != ctx["leaseId"]

    continued = await client.post(
        f"/companion/v2/tasks/{task_id}/heartbeat",
        headers=ctx["auth"],
        json={"leaseId": new_lease, "currentStep": 3, "leaseSeconds": 60},
    )
    assert continued.status_code == 200, continued.text
    assert continued.json()["businessState"] == "RUNNING"

    after = await _load_task(app, task_id)
    frozen_after = _frozen_task_view(after)
    assert frozen_after["parameters"] == frozen_before["parameters"], "parameters must not drift"
    assert frozen_after["snapshot"] == frozen_before["snapshot"], "snapshot hash must not drift"
    assert frozen_after["pin"] == frozen_before["pin"], "recipe pin must survive resume"
    assert frozen_after["steps"] == frozen_before["steps"], "real steps must not drift"
    assert after.attempt == before.attempt, "resume continues the same attempt"
    assert after.attempt_id == before.attempt_id

    completed = await client.post(
        f"/companion/v2/tasks/{task_id}/complete",
        headers=ctx["auth"],
        json={"leaseId": new_lease, "result": {"outcome": "ok"}},
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "SUCCEEDED"
    ledger.record(
        "same-task-recovery",
        taskId=task_id,
        attempt=after.attempt,
        attemptId=after.attempt_id,
        resumeCount=1,
        oldLease=ctx["leaseId"],
        newLease=new_lease,
        snapshotSha256=frozen_after["snapshot"],
    )


async def test_s07b_lost_lease_reclaim_same_task_pin_and_payload_frozen(
    api: tuple[httpx.AsyncClient, FastAPI], ledger
) -> None:
    client, app = api
    ctx = await running_steps_task(api)
    task_id = ctx["taskId"]
    before = await _load_task(app, task_id)
    frozen_before = _frozen_task_view(before)

    await expire_lease(app, task_id)
    reclaimed = await claim(client, ctx["auth"])
    assert reclaimed["taskId"] == task_id
    assert reclaimed["attempt"] == before.attempt + 1, "re-claim increments the attempt"

    after = await _load_task(app, task_id)
    assert after.attempt_id == before.attempt_id, "re-claim keeps the attemptId"
    frozen_after = _frozen_task_view(after)
    assert frozen_after["parameters"] == frozen_before["parameters"]
    assert frozen_after["snapshot"] == frozen_before["snapshot"]
    assert frozen_after["pin"] == frozen_before["pin"]
    assert after.business_state == "PREFLIGHT"
    ledger.record(
        "lost-lease-reclaim",
        taskId=task_id,
        attemptBefore=before.attempt,
        attemptAfter=after.attempt,
        attemptId=after.attempt_id,
        pinPreserved=frozen_after["pin"] is not None,
    )
