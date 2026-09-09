"""P09 contract p09-reconcile/20260910.1: uncertainty cannot be cleared by telemetry."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from cloudctl_api.db import DeviceLeaseRow, MobileTaskRow
from fastapi import FastAPI
from test_platform_tasks import (
    PROBE,
    _enroll,
    api,  # noqa: F401 - shared disposable SQLite API fixture
    bind,
    create_account,
    create_direct_device,
    identity,
)


@pytest.fixture
async def claimed(api: tuple[httpx.AsyncClient, FastAPI]):
    client, app = api
    device = await create_direct_device(client, "p09-control")
    account = await create_account(client, "p09-control")
    await bind(client, account, device)
    created = await client.post(
        "/api/v1/platform-tasks",
        headers={**identity(), "Idempotency-Key": "p09-probe"},
        json={"deviceId": device, "accountId": account, **PROBE},
    )
    assert created.status_code == 201, created.text
    task_id = created.json()["items"][0]["taskId"]
    auth = await _enroll(client, device, "p09-instance")
    response = await client.post("/companion/v2/tasks/claim", headers=auth, json={"leaseSeconds": 60})
    assert response.status_code == 200, response.text
    assert response.json()["taskId"] == task_id
    return client, app, task_id, auth, response.json()["leaseId"]


async def snapshot(app: FastAPI, task_id: str) -> dict:
    async with app.state.database.unit_of_work() as session:
        row = await session.get(MobileTaskRow, task_id)
        lease = await session.get(DeviceLeaseRow, row.device_id)
        return {
            "state": row.business_state,
            "status": row.status,
            "result": row.result,
            "error": row.error_code,
            "completed": row.completed_at,
            "sequence": row.last_sequence,
            "step": row.current_step,
            "lease": row.lease_id,
            "expires": row.lease_expires_at,
            "leaseCanceled": lease.canceled_at,
            "pin": row.recipe_pin,
            "mode": row.control_mode,
            "pauseAck": row.pause_ack_at,
            "reconciliation": row.reconciliation,
        }


async def enter_reconciliation(client, task_id, auth, lease_id):
    response = await client.post(
        f"/companion/v2/tasks/{task_id}/events", headers=auth,
        json={"leaseId": lease_id, "sequence": 1, "eventType": "RECONCILING", "payload": {}},
    )
    assert response.status_code == 201, response.text


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint,body", [
    ("complete", {"result": {"resultType": "DeviceProbeResult", "outcome": "ok"}}),
    ("fail", {"errorCode": "STEP_TIMEOUT", "detail": "ordinary runner failure"}),
])
async def test_reconciling_refuses_ordinary_finish(claimed, endpoint, body):
    client, app, task_id, auth, lease_id = claimed
    await enter_reconciliation(client, task_id, auth, lease_id)
    before = await snapshot(app, task_id)
    response = await client.post(
        f"/companion/v2/tasks/{task_id}/{endpoint}", headers=auth,
        json={"leaseId": lease_id, **body},
    )
    assert response.status_code == 409, response.text
    assert await snapshot(app, task_id) == before


@pytest.mark.asyncio
@pytest.mark.parametrize("event_type", ["PAUSE_REQUESTED", "PAUSED_WAITING_USER", "RESUME_CHECK"])
async def test_reconciling_refuses_mobile_state_changes_without_consuming_sequence(claimed, event_type):
    client, app, task_id, auth, lease_id = claimed
    await enter_reconciliation(client, task_id, auth, lease_id)
    before = await snapshot(app, task_id)
    response = await client.post(
        f"/companion/v2/tasks/{task_id}/events", headers=auth,
        json={"leaseId": lease_id, "sequence": 2, "eventType": event_type, "payload": {}},
    )
    assert response.status_code == 409, response.text
    assert await snapshot(app, task_id) == before


@pytest.mark.asyncio
@pytest.mark.parametrize("operation,body", [
    ("pause", {"reason": "ordinary pause"}),
    ("cancel", {"reason": "ordinary cancellation"}),
    ("resume", {"reason": "ordinary resume", "pageVerified": True}),
    ("ack-paused", {}),
    ("retry", {"reason": "ordinary retry"}),
])
async def test_reconciling_refuses_operator_controls(claimed, operation, body):
    client, app, task_id, auth, lease_id = claimed
    await enter_reconciliation(client, task_id, auth, lease_id)
    before = await snapshot(app, task_id)
    response = await client.post(
        f"/api/v1/platform-tasks/{task_id}:{operation}", headers=identity(), json=body,
    )
    assert response.status_code == 409, response.text
    assert await snapshot(app, task_id) == before


@pytest.mark.asyncio
async def test_reconciling_telemetry_and_replays_preserve_state_and_lease_ownership(claimed):
    client, app, task_id, auth, lease_id = claimed
    url = f"/companion/v2/tasks/{task_id}/events"
    pause = {"leaseId": lease_id, "sequence": 1, "eventType": "PAUSE_REQUESTED", "payload": {}}
    assert (await client.post(url, headers=auth, json=pause)).status_code == 201
    unknown = await client.post(
        f"/api/v1/platform-tasks/{task_id}:mark-unknown", headers=identity(),
        json={"reason": "postcondition missing"},
    )
    assert unknown.status_code == 200, unknown.text
    before = await snapshot(app, task_id)
    replay = await client.post(url, headers=auth, json=pause)
    assert replay.status_code == 200
    assert replay.headers["Idempotency-Replayed"] == "true"
    assert await snapshot(app, task_id) == before
    changed = await client.post(url, headers=auth, json={**pause, "payload": {"reason": "different"}})
    assert changed.status_code == 409
    assert (await client.post(url, headers=auth, json={**pause, "leaseId": "wrong"})).status_code == 409
    other_device = await create_direct_device(client, "p09-other")
    other_auth = await _enroll(client, other_device, "p09-other-instance")
    assert (await client.post(url, headers=other_auth, json=pause)).status_code == 404

    for sequence, event_type in enumerate(["STEP_STARTED", "STEP_SUCCEEDED", "STEP_FAILED", "LOG", "EVIDENCE"], 2):
        event = {"leaseId": lease_id, "sequence": sequence, "eventType": event_type,
                 "stepIndex": 0, "payload": {"messageCode": "OBSERVED"}}
        gap = await client.post(url, headers=auth, json={**event, "sequence": sequence + 1})
        assert gap.status_code == 409
        accepted = await client.post(url, headers=auth, json=event)
        assert accepted.status_code == 201, accepted.text
        assert (await client.post(url, headers=auth, json=event)).status_code == 200
        after = await snapshot(app, task_id)
        assert after == {**before, "sequence": sequence, "step": 0}

    heartbeat = await client.post(
        f"/companion/v2/tasks/{task_id}/heartbeat", headers=auth,
        json={"leaseId": lease_id, "currentStep": 0, "leaseSeconds": 120},
    )
    assert heartbeat.status_code == 200, heartbeat.text
    after = await snapshot(app, task_id)
    assert after["state"] == "RECONCILING"
    assert after["lease"] == lease_id and after["leaseCanceled"] is None
    assert after["pin"] == before["pin"]
    assert after["expires"] > before["expires"]
    assert (await client.post("/companion/v2/tasks/claim", headers=auth, json={})).status_code == 204

    async with app.state.database.unit_of_work() as session:
        row = await session.get(MobileTaskRow, task_id)
        row.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    expired = await client.post(url, headers=auth, json=pause)
    assert expired.status_code == 409


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["SUCCEEDED", "FAILED", "CANCELLED", "EXPIRED"])
async def test_terminal_business_state_cannot_be_reopened_by_late_runner_updates(claimed, state):
    client, app, task_id, auth, lease_id = claimed
    # Deliberately keep the old runner status and valid lease: business state is authoritative.
    async with app.state.database.unit_of_work() as session:
        row = await session.get(MobileTaskRow, task_id)
        row.business_state = state
    before = await snapshot(app, task_id)
    for event_type in ["PAUSE_REQUESTED", "PAUSED_WAITING_USER", "RESUME_CHECK", "RECONCILING", "LOG"]:
        response = await client.post(
            f"/companion/v2/tasks/{task_id}/events", headers=auth,
            json={"leaseId": lease_id, "sequence": 1, "eventType": event_type, "payload": {}},
        )
        assert response.status_code == 409, response.text
    for endpoint, body in [
        ("heartbeat", {}), ("complete", {"result": {}}),
        ("fail", {"errorCode": "STEP_TIMEOUT", "detail": "late failure"}),
    ]:
        response = await client.post(
            f"/companion/v2/tasks/{task_id}/{endpoint}", headers=auth,
            json={"leaseId": lease_id, **body},
        )
        assert response.status_code == 409, response.text
    unknown = await client.post(
        f"/api/v1/platform-tasks/{task_id}:mark-unknown", headers=identity(),
        json={"reason": "late uncertainty"},
    )
    assert unknown.status_code == 409
    assert await snapshot(app, task_id) == before


@pytest.mark.asyncio
@pytest.mark.parametrize("decision,state", [
    ("CONFIRMED_APPLIED", "SUCCEEDED"), ("CONFIRMED_NOT_SUBMITTED", "FAILED"),
])
async def test_explicit_evidence_reconcile_is_only_exit_and_cannot_reopen_terminal(claimed, decision, state):
    client, app, task_id, auth, lease_id = claimed
    await enter_reconciliation(client, task_id, auth, lease_id)
    # Legacy failures can retain this code after explicit confirmation; it must not reopen a terminal row.
    async with app.state.database.unit_of_work() as session:
        row = await session.get(MobileTaskRow, task_id)
        row.error_code = "COMMIT_UNKNOWN"
    url = f"/api/v1/platform-tasks/{task_id}:reconcile"
    waiting = await client.post(url, headers=identity(), json={
        "decision": "KEEP_WAITING", "evidence": "no unique postcondition evidence yet",
    })
    assert waiting.status_code == 200 and waiting.json()["state"] == "RECONCILING"
    missing = await client.post(url, headers=identity(), json={
        "decision": "CONFIRMED_APPLIED", "evidence": "ambiguous observation",
    })
    assert missing.status_code == 409
    body = {"decision": decision, "evidence": "test operator recorded unique postcondition evidence"}
    if decision == "CONFIRMED_APPLIED":
        body["platformItemId"] = "p09-evidence-item"
    resolved = await client.post(url, headers=identity(), json=body)
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["state"] == state
    assert len(resolved.json()["reconciliation"]["history"]) == 2
    before = await snapshot(app, task_id)
    reopened = await client.post(url, headers=identity(), json={
        "decision": "KEEP_WAITING", "evidence": "late evidence report",
    })
    assert reopened.status_code == 409
    assert await snapshot(app, task_id) == before


@pytest.mark.asyncio
async def test_reconciling_with_failed_runner_cannot_bypass_finish_or_retry_guards(claimed):
    client, app, task_id, auth, lease_id = claimed
    await enter_reconciliation(client, task_id, auth, lease_id)
    async with app.state.database.unit_of_work() as session:
        row = await session.get(MobileTaskRow, task_id)
        row.status = "FAILED"
        row.result = {}
        row.error_code = "STEP_TIMEOUT"
        row.detail = "old failure"
    before = await snapshot(app, task_id)
    finished = await client.post(
        f"/companion/v2/tasks/{task_id}/fail", headers=auth,
        json={"leaseId": lease_id, "errorCode": "STEP_TIMEOUT", "detail": "old failure"},
    )
    assert finished.status_code == 409
    retry = await client.post(
        f"/api/v1/platform-tasks/{task_id}:retry", headers=identity(), json={"reason": "retry failed runner"},
    )
    assert retry.status_code == 409
    assert await snapshot(app, task_id) == before


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint,body", [
    ("complete", {"result": {"resultType": "DeviceProbeResult", "outcome": "ok"}}),
    ("fail", {"errorCode": "STEP_TIMEOUT", "detail": "ordinary failure"}),
])
async def test_ordinary_terminal_finish_replay_remains_idempotent(claimed, endpoint, body):
    client, app, task_id, auth, lease_id = claimed
    url = f"/companion/v2/tasks/{task_id}/{endpoint}"
    first = await client.post(url, headers=auth, json={"leaseId": lease_id, **body})
    assert first.status_code == 200, first.text
    before = await snapshot(app, task_id)
    replay = await client.post(url, headers=auth, json={"leaseId": lease_id, **body})
    assert replay.status_code == 200 and replay.json() == first.json()
    assert await snapshot(app, task_id) == before
    event = await client.post(
        f"/companion/v2/tasks/{task_id}/events", headers=auth,
        json={"leaseId": lease_id, "sequence": 1, "eventType": "RECONCILING", "payload": {}},
    )
    assert event.status_code == 409
    assert await snapshot(app, task_id) == before
