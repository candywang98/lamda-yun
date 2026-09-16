"""Q02 scenario 4 (class A): cancellation semantics across the state matrix.

Not-yet-running states land in CANCELLED immediately and replay idempotently;
RUNNING degrades to CANCEL_REQUESTED; RECONCILING refuses cancellation until
the operator resolves the uncertain result; terminal states refuse (except
CANCELLED, which is idempotent).
"""

from __future__ import annotations

import httpx
import pytest
from cloudctl_api.db import MobileTaskRow
from fastapi import FastAPI

from .conftest import bind, create_account, create_direct_device, enroll, identity
from .harness import running_steps_task

PROBE = {
    "commandType": "device.probe_capabilities.v1",
    "parameters": {},
}


async def _mint(client: httpx.AsyncClient, device_id: str, account: str, key: str) -> str:
    created = await client.post(
        "/api/v1/platform-tasks",
        headers={**identity(), "Idempotency-Key": key},
        json={"deviceId": device_id, "accountId": account, **PROBE},
    )
    assert created.status_code == 201, created.text
    return str(created.json()["items"][0]["taskId"])


async def _drive_to(
    api: tuple[httpx.AsyncClient, FastAPI], device_id: str, task_id: str, state: str
) -> None:
    """Move a freshly minted task into the requested business state."""
    client, app = api
    if state == "QUEUED":
        return
    auth = await enroll(client, device_id, f"instance-{state.lower()}")
    claimed = await client.post(
        "/companion/v2/tasks/claim", headers=auth, json={"leaseSeconds": 60}
    )
    assert claimed.status_code == 200, claimed.text
    assert claimed.json()["taskId"] == task_id
    lease_id = claimed.json()["leaseId"]
    if state == "PREFLIGHT":
        return
    started = await client.post(
        f"/companion/v2/tasks/{task_id}/heartbeat",
        headers=auth,
        json={"leaseId": lease_id, "currentStep": 0, "leaseSeconds": 60},
    )
    assert started.status_code == 200, started.text
    if state == "RUNNING":
        return
    if state in {"PAUSE_REQUESTED", "PAUSED_WAITING_USER"}:
        paused = await client.post(
            f"/api/v1/platform-tasks/{task_id}:pause",
            headers=identity(),
            json={"reason": "operator taking over"},
        )
        assert paused.status_code == 200, paused.text
        if state == "PAUSE_REQUESTED":
            return
        acked = await client.post(
            f"/api/v1/platform-tasks/{task_id}:ack-paused",
            headers=identity(),
            json={"leaseId": lease_id},
        )
        assert acked.status_code == 200, acked.text
        return
    # States the API cannot reach from a healthy runner are staged directly.
    async with app.state.database.unit_of_work() as session:
        row = await session.get(MobileTaskRow, task_id)
        assert row is not None
        row.business_state = state
        if state == "SUCCEEDED":
            row.status = "SUCCEEDED"
        elif state == "FAILED":
            row.status = "FAILED"
            row.error_code = "STEP_TIMEOUT"


async def _cancel(client: httpx.AsyncClient, task_id: str, reason: str) -> httpx.Response:
    return await client.post(
        f"/api/v1/platform-tasks/{task_id}:cancel", headers=identity(), json={"reason": reason}
    )


@pytest.mark.parametrize(
    ("initial", "expected_state", "expected_status"),
    [
        ("QUEUED", "CANCELLED", 200),
        ("WAITING_MATERIALS", "CANCELLED", 200),
        ("PREFLIGHT", "CANCELLED", 200),
        ("PAUSE_REQUESTED", "CANCELLED", 200),
        ("PAUSED_WAITING_USER", "CANCELLED", 200),
        ("RUNNING", "CANCEL_REQUESTED", 200),
        ("RECONCILING", None, 409),
        ("SUCCEEDED", None, 409),
        ("FAILED", None, 409),
    ],
)
async def test_s04_cancel_matrix(
    api: tuple[httpx.AsyncClient, FastAPI],
    ledger,
    initial: str,
    expected_state: str | None,
    expected_status: int,
) -> None:
    client, _ = api
    suffix = initial.lower()
    device_id = await create_direct_device(client, f"phone-s04-{suffix}")
    account = await create_account(client, f"xy-s04-{suffix}")
    await bind(client, account, device_id)
    task_id = await _mint(client, device_id, account, f"s04-{suffix}")
    await _drive_to(api, device_id, task_id, initial)

    response = await _cancel(client, task_id, f"s04 matrix cancel from {initial}")
    assert response.status_code == expected_status, response.text
    if expected_state is not None:
        assert response.json()["state"] == expected_state
    ledger.record(
        "cancel-matrix",
        taskId=task_id,
        initial=initial,
        resultState=response.json().get("state"),
        httpStatus=expected_status,
    )

    if initial == "RUNNING":
        # CANCEL_REQUESTED must not be pause-acked by the companion.
        ack = await client.post(
            f"/api/v1/platform-tasks/{task_id}:ack-paused", headers=identity(), json={}
        )
        assert ack.status_code == 409, ack.text
    if initial == "RECONCILING":
        assert "reconcil" in response.json()["detail"].lower()


async def test_s04_cancelled_replay_is_idempotent(
    api: tuple[httpx.AsyncClient, FastAPI], ledger
) -> None:
    client, app = api
    device_id = await create_direct_device(client, "phone-s04-replay")
    account = await create_account(client, "xy-s04-replay")
    await bind(client, account, device_id)
    task_id = await _mint(client, device_id, account, "s04-replay")

    first = await _cancel(client, task_id, "operator stopped before claim")
    assert first.status_code == 200, first.text
    assert first.json()["state"] == "CANCELLED"
    replay = await _cancel(client, task_id, "operator stopped before claim")
    assert replay.status_code == 200, replay.text
    assert replay.json()["state"] == "CANCELLED"

    async with app.state.database.unit_of_work() as session:
        row = await session.get(MobileTaskRow, task_id)
        assert row is not None
        assert row.business_state == "CANCELLED"
        assert row.error_code == "CANCELLED"
        assert row.lease_id is None, "cancellation must drop the lease"
    ledger.record("cancel-replay-idempotent", taskId=task_id)


async def test_s04_cancelled_task_never_reaches_companion(
    api: tuple[httpx.AsyncClient, FastAPI], ledger
) -> None:
    """A task cancelled before claim must not be handed to any runner."""
    client, _ = api
    ctx = await running_steps_task(api, with_heartbeat=False)
    cancelled = await _cancel(client, ctx["taskId"], "stopped before claim")
    assert cancelled.status_code == 200, cancelled.text
    blocked = await client.post(
        "/companion/v2/tasks/claim", headers=ctx["auth"], json={"leaseSeconds": 60}
    )
    assert blocked.status_code == 204, blocked.text
    ledger.record("cancelled-not-claimable", taskId=ctx["taskId"])
