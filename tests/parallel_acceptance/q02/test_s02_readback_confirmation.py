"""Q02 scenario 2 (class A): readback confirmation after a controlled action.

The controlled platform contract: an APPLIED outcome must be backed by an
independent postcondition readback (badge delta / publish-success node), an
outcome that reuses the before-evidence is refused, and an inconclusive
readback lands as UNKNOWN + RECONCILING which complete/fail cannot bypass.
The platform side is played by the mock stub in mock_platform.py.
"""

from __future__ import annotations

import httpx
from cloudctl_api.db import MobileActionCommitRow, MobileTaskRow
from fastapi import FastAPI
from sqlalchemy import select

from .harness import action_paths, intent_body, running_steps_task
from .mock_platform import BadgeReadbackStub, PostconditionReadbackStub


async def _report(ctx: dict, body: dict, status: str, evidence: str) -> dict:
    return {
        "leaseId": ctx["leaseId"],
        "parameterHash": body["parameterHash"],
        "status": status,
        "evidence": evidence,
    }


async def test_s02a_applied_requires_independent_readback_evidence(
    api: tuple[httpx.AsyncClient, FastAPI], ledger
) -> None:
    client, _ = api
    ctx = await running_steps_task(api)
    readback = PostconditionReadbackStub(postcondition_present=True)
    body = intent_body(ctx, before_evidence=readback.before_evidence())
    intent, action = action_paths(ctx)
    authorized = await client.post(intent, headers=ctx["auth"], json=body)
    assert authorized.status_code == 201, authorized.text
    before = authorized.json()["action"]

    reused = await _report(ctx, body, "APPLIED", before["beforeEvidence"])
    refused = await client.post(action + "/outcome", headers=ctx["auth"], json=reused)
    assert refused.status_code == 409, refused.text
    assert "independent postcondition evidence" in refused.json()["detail"]

    status, evidence = readback.verdict()
    assert status == "APPLIED"
    assert evidence != before["beforeEvidence"]
    confirmed = await client.post(
        action + "/outcome", headers=ctx["auth"], json=await _report(ctx, body, status, evidence)
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == "APPLIED"
    assert confirmed.json()["reportedEvidence"] == evidence
    ledger.record_action(ctx["taskId"], confirmed.json(), scenario="s02-readback")
    ledger.record(
        "readback-confirmed",
        taskId=ctx["taskId"],
        beforeEvidence=before["beforeEvidence"],
        afterEvidence=evidence,
    )


async def test_s02b_badge_delta_readback_drives_verdict(
    api: tuple[httpx.AsyncClient, FastAPI], ledger
) -> None:
    """Badge readback semantics (delist shape, expectedDelta -1) via the stub."""
    matching = BadgeReadbackStub(badge_before=5, badge_after=4)
    assert matching.observed_delta() == -1
    status, evidence = matching.verdict()
    assert status == "APPLIED"
    assert evidence == "xianyu_pub_tab_onsale@after=4"
    assert evidence != matching.before_evidence()

    inconclusive = BadgeReadbackStub(badge_before=5, badge_after=5)
    status, evidence = inconclusive.verdict()
    assert status == "UNKNOWN"
    assert "readback-inconclusive" in evidence
    ledger.record(
        "badge-readback-verdicts",
        matching="APPLIED",
        inconclusive="UNKNOWN",
        expectedDelta=-1,
    )


async def test_s02c_inconclusive_readback_is_unknown_and_blocks_completion(
    api: tuple[httpx.AsyncClient, FastAPI], ledger
) -> None:
    client, app = api
    ctx = await running_steps_task(api)
    readback = PostconditionReadbackStub(postcondition_present=False)
    body = intent_body(ctx, before_evidence=readback.before_evidence())
    intent, action = action_paths(ctx)
    assert (await client.post(intent, headers=ctx["auth"], json=body)).status_code == 201

    status, evidence = readback.verdict()
    assert status == "UNKNOWN"
    outcome = await client.post(
        action + "/outcome", headers=ctx["auth"], json=await _report(ctx, body, status, evidence)
    )
    assert outcome.status_code == 200, outcome.text
    assert outcome.json()["status"] == "UNKNOWN"

    completion = await client.post(
        f"/companion/v2/tasks/{ctx['taskId']}/complete",
        headers=ctx["auth"],
        json={"leaseId": ctx["leaseId"], "result": {"outcome": "ok"}},
    )
    assert completion.status_code == 409, completion.text
    assert "reconcil" in completion.json()["detail"].lower()

    failure = await client.post(
        f"/companion/v2/tasks/{ctx['taskId']}/fail",
        headers=ctx["auth"],
        json={
            "leaseId": ctx["leaseId"],
            "errorCode": "STEP_TIMEOUT",
            "detail": "must not mask an unknown commit",
        },
    )
    assert failure.status_code == 409, failure.text

    async with app.state.database.unit_of_work() as session:
        task = await session.get(MobileTaskRow, ctx["taskId"])
        assert task is not None
        assert task.business_state == "RECONCILING"
        row = await session.get(MobileActionCommitRow, body["actionKey"])
        assert row is not None
        assert row.status == "UNKNOWN"
        assert row.resolution_revision == 0
    ledger.record_action(
        ctx["taskId"], outcome.json(), scenario="s02-readback", terminal="blocked-pending-operator"
    )


async def test_s02d_outcome_replay_is_idempotent_content_locked(
    api: tuple[httpx.AsyncClient, FastAPI], ledger
) -> None:
    client, app = api
    ctx = await running_steps_task(api)
    readback = PostconditionReadbackStub(postcondition_present=True)
    body = intent_body(ctx, before_evidence=readback.before_evidence())
    intent, action = action_paths(ctx)
    assert (await client.post(intent, headers=ctx["auth"], json=body)).status_code == 201
    status, evidence = readback.verdict()
    report = await _report(ctx, body, status, evidence)

    first = await client.post(action + "/outcome", headers=ctx["auth"], json=report)
    assert first.status_code == 200, first.text
    duplicate = await client.post(action + "/outcome", headers=ctx["auth"], json=report)
    assert duplicate.status_code == 200, duplicate.text
    assert duplicate.json() == first.json()

    conflicting = await client.post(
        action + "/outcome",
        headers=ctx["auth"],
        json=await _report(ctx, body, "UNKNOWN", "evidence://changed-mid-flight"),
    )
    assert conflicting.status_code == 409, conflicting.text

    async with app.state.database.unit_of_work() as session:
        rows = list(
            await session.scalars(
                select(MobileActionCommitRow).where(
                    MobileActionCommitRow.task_id == ctx["taskId"]
                )
            )
        )
        assert len(rows) == 1
        assert rows[0].status == "APPLIED"
    ledger.record_action(ctx["taskId"], first.json(), scenario="s02-readback")
