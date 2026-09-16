"""Q02 scenario 1 (class A): intent ordering on the controlled ledger.

Acceptance: within one task the GATED intent is authorized exactly once;
replays reconcile instead of re-authorizing, and out-of-order companion
traffic (outcome before intent, gapped/replayed event sequences, intent on a
non-RUNNING task) is rejected or idempotently ignored - never duplicated.
"""

from __future__ import annotations

import uuid

import httpx
import pytest
from cloudctl_api.db import AuditEventRow, MobileActionCommitRow, MobileTaskRow
from fastapi import FastAPI
from sqlalchemy import select

from .harness import action_paths, intent_body, post_event, running_steps_task
from .mock_platform import PostconditionReadbackStub


async def test_s01a_gated_intent_authorized_exactly_once(
    api: tuple[httpx.AsyncClient, FastAPI], ledger
) -> None:
    client, app = api
    ctx = await running_steps_task(api)
    assert ctx["heartbeat"]["businessState"] == "RUNNING"
    readback = PostconditionReadbackStub(postcondition_present=True)
    body = intent_body(ctx, before_evidence=readback.before_evidence())
    intent, action = action_paths(ctx)

    first = await client.post(intent, headers=ctx["auth"], json=body)
    assert first.status_code == 201, first.text
    assert first.json()["decision"] == "AUTHORIZED"
    action_view = first.json()["action"]
    assert action_view["status"] == "INTENT"
    assert action_view["resolutionRevision"] == 0

    replay = await client.post(intent, headers=ctx["auth"], json=body)
    assert replay.status_code == 200, replay.text
    assert replay.json()["decision"] == "RECONCILE_REQUIRED"
    assert replay.json()["action"]["actionKey"] == action_view["actionKey"]

    ledger.record_action(ctx["taskId"], action_view, scenario="s01-intent-order")

    async with app.state.database.unit_of_work() as session:
        rows = list(
            await session.scalars(
                select(MobileActionCommitRow).where(
                    MobileActionCommitRow.task_id == ctx["taskId"]
                )
            )
        )
        assert len(rows) == 1, "GATED intent must create exactly one ledger row"
        assert rows[0].status == "INTENT"
        assert rows[0].action_key == action_view["actionKey"]
        audits = list(
            await session.scalars(
                select(AuditEventRow).where(
                    AuditEventRow.resource_id == action_view["actionKey"]
                )
            )
        )
        assert [a.action for a in audits] == ["mobile.action.intent"], (
            "replayed intent must not append another audit row"
        )
        task = await session.get(MobileTaskRow, ctx["taskId"])
        assert task is not None
        assert task.business_state == "RECONCILING"


async def test_s01b_outcome_before_intent_is_not_found(
    api: tuple[httpx.AsyncClient, FastAPI], ledger
) -> None:
    client, _ = api
    ctx = await running_steps_task(api)
    readback = PostconditionReadbackStub(postcondition_present=True)
    body = intent_body(ctx, before_evidence=readback.before_evidence())
    _, action = action_paths(ctx)
    report = {
        "leaseId": ctx["leaseId"],
        "parameterHash": body["parameterHash"],
        "status": "APPLIED",
        "evidence": readback.verdict()[1],
    }
    early = await client.post(action + "/outcome", headers=ctx["auth"], json=report)
    assert early.status_code == 404, early.text
    ledger.record("outcome-before-intent-rejected", taskId=ctx["taskId"])


async def test_s01c_event_sequence_out_of_order_rejected(
    api: tuple[httpx.AsyncClient, FastAPI], ledger
) -> None:
    client, app = api
    ctx = await running_steps_task(api)

    gap = await post_event(client, ctx, 2, "LOG", {"stepId": "fill-description"})
    assert gap.status_code == 409, gap.text
    assert "gap" in gap.json()["detail"]

    first = await post_event(client, ctx, 1, "LOG", {"stepId": "fill-description"})
    assert first.status_code == 201, first.text

    duplicate = await post_event(client, ctx, 1, "LOG", {"stepId": "fill-description"})
    assert duplicate.status_code == 200, duplicate.text
    assert duplicate.headers["Idempotency-Replayed"] == "true"

    mutated = await post_event(client, ctx, 1, "LOG", {"stepId": "click-publish"})
    assert mutated.status_code == 409, mutated.text
    assert "replayed with different content" in mutated.json()["detail"]

    skip = await post_event(client, ctx, 3, "LOG", {"stepId": "wait-publish-complete"})
    assert skip.status_code == 409, skip.text

    third = await post_event(client, ctx, 2, "LOG", {"stepId": "click-publish"})
    assert third.status_code == 201, third.text
    ledger.record("event-sequence-monotonic", taskId=ctx["taskId"])

    from cloudctl_api.db import MobileTaskEventRow

    async with app.state.database.unit_of_work() as session:
        events = list(
            await session.scalars(
                select(MobileTaskEventRow)
                .where(MobileTaskEventRow.task_id == ctx["taskId"])
                .order_by(MobileTaskEventRow.sequence)
            )
        )
        assert [event.sequence for event in events] == [1, 2]


async def test_s01d_intent_requires_running_task_and_frozen_replay(
    api: tuple[httpx.AsyncClient, FastAPI], ledger
) -> None:
    client, app = api
    queued = await running_steps_task(api, with_heartbeat=False)
    queued_body = intent_body(queued, before_evidence="evidence://before")
    intent, _ = action_paths(queued)
    denied = await client.post(intent, headers=queued["auth"], json=queued_body)
    assert denied.status_code == 409, denied.text
    assert "RUNNING" in denied.json()["detail"]

    ctx = await running_steps_task(api)
    readback = PostconditionReadbackStub(postcondition_present=True)
    body = intent_body(ctx, before_evidence=readback.before_evidence())
    intent, _ = action_paths(ctx)
    assert (await client.post(intent, headers=ctx["auth"], json=body)).status_code == 201

    drifted = {**body, "beforeEvidence": "evidence://different"}
    assert (
        await client.post(intent, headers=ctx["auth"], json=drifted)
    ).status_code == 409

    stale_lease = {**body, "leaseId": str(uuid.uuid4())}
    assert (
        await client.post(intent, headers=ctx["auth"], json=stale_lease)
    ).status_code == 409

    wrong_action = {**body, "actionId": "not-the-gated-action"}
    assert (
        await client.post(intent, headers=ctx["auth"], json=wrong_action)
    ).status_code == 409

    async with app.state.database.unit_of_work() as session:
        count = len(
            list(
                await session.scalars(
                    select(MobileActionCommitRow).where(
                        MobileActionCommitRow.task_id == ctx["taskId"]
                    )
                )
            )
        )
        assert count == 1, "rejected replays must not create extra ledger rows"
    ledger.record("frozen-replay-rejected", taskId=ctx["taskId"])


@pytest.mark.parametrize(
    "forged", ["actionKey", "parameterHash"], ids=["forged-action-key", "forged-parameter-hash"]
)
async def test_s01e_forged_identity_never_enters_the_ledger(
    api: tuple[httpx.AsyncClient, FastAPI], ledger, forged: str
) -> None:
    client, app = api
    ctx = await running_steps_task(api)
    readback = PostconditionReadbackStub(postcondition_present=True)
    body = intent_body(ctx, before_evidence=readback.before_evidence())
    body[forged] = "0" * 64
    intent, _ = action_paths(ctx)
    response = await client.post(intent, headers=ctx["auth"], json=body)
    assert response.status_code == 409, response.text
    async with app.state.database.unit_of_work() as session:
        rows = list(
            await session.scalars(
                select(MobileActionCommitRow).where(
                    MobileActionCommitRow.task_id == ctx["taskId"]
                )
            )
        )
        assert rows == []
        task = await session.get(MobileTaskRow, ctx["taskId"])
        assert task is not None
        assert task.business_state == "RUNNING"
    ledger.record("forged-identity-refused", taskId=ctx["taskId"], field=forged)


async def test_s01f_reconciling_task_is_not_claimable_second_runner(
    api: tuple[httpx.AsyncClient, FastAPI], ledger
) -> None:
    """UNKNOWN on both ends must not be bypassed by re-claiming the queue."""
    client, _ = api
    ctx = await running_steps_task(api)
    readback = PostconditionReadbackStub(postcondition_present=False)
    body = intent_body(ctx, before_evidence=readback.before_evidence())
    intent, action = action_paths(ctx)
    assert (await client.post(intent, headers=ctx["auth"], json=body)).status_code == 201
    status, evidence = readback.verdict()
    report = {
        "leaseId": ctx["leaseId"],
        "parameterHash": body["parameterHash"],
        "status": status,
        "evidence": evidence,
    }
    outcome = await client.post(action + "/outcome", headers=ctx["auth"], json=report)
    assert outcome.status_code == 200, outcome.text
    assert outcome.json()["status"] == "UNKNOWN"
    # A second claim attempt (duplicate runner) must not receive this task.
    # fleet-identity/v1 §8 (A10): open UNKNOWN now fails closed with 409
    # RECONCILE_REQUIRED instead of a silent 204.
    blocked = await client.post(
        "/companion/v2/tasks/claim", headers=ctx["auth"], json={"leaseSeconds": 60}
    )
    assert blocked.status_code == 409, blocked.text
    assert blocked.json()["code"] == "RECONCILE_REQUIRED", blocked.text
    ledger.record_action(ctx["taskId"], outcome.json(), scenario="s01-intent-order")
