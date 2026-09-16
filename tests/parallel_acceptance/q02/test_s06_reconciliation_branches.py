"""Q02 scenario 6 (class A): operator reconciliation of an UNKNOWN commit.

The three frozen decisions land correctly in the database:
CONFIRMED_NOT_SUBMITTED -> FAILED with ledger NOT_SUBMITTED;
CONFIRMED_APPLIED (requires a unique platformItemId) -> SUCCEEDED with ledger
APPLIED; KEEP_WAITING stays RECONCILING with the ledger untouched. Both ends
UNKNOWN is never bypassed (no cancel/retry/resume/complete/claim) and never
resolved twice. An APPLIED report contradicts CONFIRMED_NOT_SUBMITTED.
"""

from __future__ import annotations

import httpx
import pytest
from cloudctl_api.db import AuditEventRow, MobileActionCommitRow, MobileTaskRow
from fastapi import FastAPI
from sqlalchemy import select

from .conftest import identity
from .harness import action_paths, intent_body, running_steps_task
from .mock_platform import BadgeReadbackStub, PostconditionReadbackStub


async def _unknown_task(
    api: tuple[httpx.AsyncClient, FastAPI], *, applied: bool = False
) -> dict:
    """Running task with one gated action reported UNKNOWN (or APPLIED)."""
    client, _ = api
    readback = PostconditionReadbackStub(postcondition_present=applied)
    ctx = await running_steps_task(api)
    body = intent_body(ctx, before_evidence=readback.before_evidence())
    intent, action = action_paths(ctx)
    assert (await client.post(intent, headers=ctx["auth"], json=body)).status_code == 201
    status, evidence = readback.verdict()
    assert status == ("APPLIED" if applied else "UNKNOWN")
    report = {
        "leaseId": ctx["leaseId"],
        "parameterHash": body["parameterHash"],
        "status": status,
        "evidence": evidence,
    }
    outcome = await client.post(action + "/outcome", headers=ctx["auth"], json=report)
    assert outcome.status_code == 200, outcome.text
    ctx["body"] = body
    ctx["outcome"] = outcome.json()
    return ctx


async def _reconcile(
    client: httpx.AsyncClient, task_id: str, decision: str, evidence: str, item: str | None = None
) -> httpx.Response:
    payload: dict = {"decision": decision, "evidence": evidence}
    if item is not None:
        payload["platformItemId"] = item
    return await client.post(
        f"/api/v1/platform-tasks/{task_id}:reconcile", headers=identity(), json=payload
    )


async def test_s06a_keep_waiting_stays_reconciling_ledger_untouched(
    api: tuple[httpx.AsyncClient, FastAPI], ledger
) -> None:
    client, app = api
    ctx = await _unknown_task(api)
    task_id = ctx["taskId"]

    first = await _reconcile(client, task_id, "KEEP_WAITING", "two similar listings, not unique")
    assert first.status_code == 200, first.text
    assert first.json()["state"] == "RECONCILING"
    assert first.json()["reconciliation"]["status"] == "KEEP_WAITING"

    async with app.state.database.unit_of_work() as session:
        row = await session.get(MobileActionCommitRow, ctx["body"]["actionKey"])
        assert row is not None
        assert row.status == "UNKNOWN"
        assert row.resolution_revision == 0
        assert row.resolution_evidence is None
        assert row.resolved_at is None
        history = (await session.get(MobileTaskRow, task_id)).reconciliation["history"]
        assert history[-1]["decision"] == "KEEP_WAITING"
        assert history[-1]["actorId"]
    ledger.record("keep-waiting", taskId=task_id, actionKey=ctx["body"]["actionKey"])


async def test_s06b_confirmed_not_submitted_lands_failed(
    api: tuple[httpx.AsyncClient, FastAPI], ledger
) -> None:
    client, app = api
    ctx = await _unknown_task(api)
    task_id = ctx["taskId"]

    resolved = await _reconcile(
        client, task_id, "CONFIRMED_NOT_SUBMITTED", "operator verified listing absent"
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["state"] == "FAILED"
    assert resolved.json()["errorCode"] == "CONFIRMED_NOT_SUBMITTED"
    assert resolved.json()["detail"] == "operator verified listing absent"

    async with app.state.database.unit_of_work() as session:
        row = await session.get(MobileActionCommitRow, ctx["body"]["actionKey"])
        assert row is not None
        assert row.status == "NOT_SUBMITTED"
        assert row.resolution_revision == 1
        assert row.resolution_evidence == "operator verified listing absent"
        assert row.resolved_at is not None
        audits = list(
            await session.scalars(
                select(AuditEventRow).where(AuditEventRow.action == "mobile.action.resolved")
            )
        )
        assert len(audits) == 1
        assert audits[0].metadata_json["resolutionRevision"] == 1

    again = await _reconcile(client, task_id, "KEEP_WAITING", "second decision")
    assert again.status_code == 409, again.text
    assert "terminal" in again.json()["detail"].lower()
    ledger.record(
        "confirmed-not-submitted", taskId=task_id, actionKey=ctx["body"]["actionKey"]
    )


async def test_s06c_confirmed_applied_requires_unique_item_then_succeeds(
    api: tuple[httpx.AsyncClient, FastAPI], ledger
) -> None:
    client, app = api
    ctx = await _unknown_task(api)
    task_id = ctx["taskId"]

    missing = await _reconcile(client, task_id, "CONFIRMED_APPLIED", "looks published")
    assert missing.status_code == 409, missing.text
    assert "platformItemId" in missing.json()["detail"]

    applied = await _reconcile(
        client,
        task_id,
        "CONFIRMED_APPLIED",
        "unique idlefish item matched snapshot",
        item="xy-item-q02-1",
    )
    assert applied.status_code == 200, applied.text
    assert applied.json()["state"] == "SUCCEEDED"
    assert applied.json()["result"]["platformItemId"] == "xy-item-q02-1"
    assert applied.json()["result"]["outcome"] == "applied"

    async with app.state.database.unit_of_work() as session:
        row = await session.get(MobileActionCommitRow, ctx["body"]["actionKey"])
        assert row is not None
        assert row.status == "APPLIED"
        assert row.resolution_revision == 1
        task = await session.get(MobileTaskRow, task_id)
        assert task is not None
        history = task.reconciliation["history"]
        assert history[-1]["platformItemId"] == "xy-item-q02-1"
        assert history[-1]["attemptId"] == task.attempt_id
    ledger.record(
        "confirmed-applied",
        taskId=task_id,
        actionKey=ctx["body"]["actionKey"],
        platformItemId="xy-item-q02-1",
    )


async def test_s06d_applied_report_contradicts_not_submitted(
    api: tuple[httpx.AsyncClient, FastAPI], ledger
) -> None:
    client, _ = api
    ctx = await _unknown_task(api, applied=True)
    contradiction = await _reconcile(
        client, ctx["taskId"], "CONFIRMED_NOT_SUBMITTED", "contradicts the applied report"
    )
    assert contradiction.status_code == 409, contradiction.text
    assert "contradicts" in contradiction.json()["detail"]
    ledger.record(
        "applied-contradiction-refused", taskId=ctx["taskId"], actionKey=ctx["body"]["actionKey"]
    )


@pytest.mark.parametrize(
    "channel",
    ["cancel", "retry", "resume", "complete", "claim"],
)
async def test_s06e_unknown_not_bypassed_by_any_channel(
    api: tuple[httpx.AsyncClient, FastAPI], ledger, channel: str
) -> None:
    client, _ = api
    ctx = await _unknown_task(api)
    task_id = ctx["taskId"]

    if channel == "cancel":
        response = await client.post(
            f"/api/v1/platform-tasks/{task_id}:cancel",
            headers=identity(),
            json={"reason": "operator wants to stop"},
        )
        assert response.status_code == 409, response.text
        assert "reconcil" in response.json()["detail"].lower()
    elif channel == "retry":
        response = await client.post(
            f"/api/v1/platform-tasks/{task_id}:retry",
            headers=identity(),
            json={"reason": "must not auto retry unknown"},
        )
        assert response.status_code == 409, response.text
    elif channel == "resume":
        response = await client.post(
            f"/api/v1/platform-tasks/{task_id}:resume",
            headers=identity(),
            json={"reason": "unknown must stay stopped", "pageVerified": True},
        )
        assert response.status_code == 409, response.text
    elif channel == "complete":
        response = await client.post(
            f"/companion/v2/tasks/{task_id}/complete",
            headers=ctx["auth"],
            json={"leaseId": ctx["leaseId"], "result": {"outcome": "ok"}},
        )
        assert response.status_code == 409, response.text
    else:
        # fleet-identity/v1 §8 (A10): open UNKNOWN claim fails closed 409.
        response = await client.post(
            "/companion/v2/tasks/claim", headers=ctx["auth"], json={"leaseSeconds": 60}
        )
        assert response.status_code == 409, response.text
        assert response.json()["code"] == "RECONCILE_REQUIRED", response.text
    ledger.record("unknown-not-bypassed", taskId=task_id, channel=channel)


async def test_s06f_reconciliation_decisions_validated(
    api: tuple[httpx.AsyncClient, FastAPI], ledger
) -> None:
    client, _ = api
    ctx = await _unknown_task(api)
    invalid = await client.post(
        f"/api/v1/platform-tasks/{ctx['taskId']}:reconcile",
        headers=identity(),
        json={"decision": "JUST_TRY_AGAIN", "evidence": "not a frozen decision"},
    )
    assert invalid.status_code == 422, invalid.text
    ledger.record("decision-validated", taskId=ctx["taskId"])


async def test_s06g_maintenance_badge_readback_unknown_then_applied(
    api: tuple[httpx.AsyncClient, FastAPI], ledger
) -> None:
    """Delist badge readback (delta -1): stub-verified APPLIED resolution path."""
    client, _ = api
    stub = BadgeReadbackStub(badge_before=5, badge_after=4)
    status, evidence = stub.verdict()
    assert status == "APPLIED", "badge delta -1 must read back as APPLIED"
    ctx = await _unknown_task(api, applied=True)
    resolved = await _reconcile(
        client,
        ctx["taskId"],
        "CONFIRMED_APPLIED",
        f"badge readback {evidence}",
        item="xy-item-q02-badge",
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["result"]["platformItemId"] == "xy-item-q02-badge"
    ledger.record(
        "badge-readback-applied",
        taskId=ctx["taskId"],
        evidence=evidence,
        platformItemId="xy-item-q02-badge",
    )
