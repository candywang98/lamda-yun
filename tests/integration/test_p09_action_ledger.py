"""Frozen p09-ledger/20260910.1; HTTP contracts and disposable PostgreSQL locking."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from cloudctl_api.db import AuditEventRow, MobileActionCommitRow, MobileTaskRow
from cloudctl_api.mobile_actions import action_identity
from sqlalchemy import select
from test_p14_recipe_versions import (  # noqa: F401 - pytest fixture injection
    api,
    change,
    claim,
    isolated_postgres,
    pg_url,
    register,
)
from test_p14_recipe_versions import (
    task as create_probe,
)
from test_platform_tasks import _enroll, create_direct_device, identity


async def running(api):  # noqa: F811 - shared fixture value
    client, app = api
    device = await create_direct_device(client, "ledger")
    auth = await _enroll(client, device, "ledger-instance")
    version = await register(client, "1.0.1")
    assert (await change(client, version, [device])).status_code == 200
    task = await create_probe(client, device)
    claimed = await claim(client, auth)
    started = await client.post(
        f"/companion/v2/tasks/{task}/heartbeat",
        headers=auth,
        json={"leaseId": claimed["leaseId"], "currentStep": 0},
    )
    assert started.status_code == 200, started.text
    async with app.state.database.unit_of_work() as session:
        row = await session.get(MobileTaskRow, task)
        key, parameters = action_identity(
            task,
            row.command_type,
            row.account_id,
            row.binding_version,
            row.command_payload["snapshotSha256"],
            row.recipe_pin["sha256"],
            "probe",
        )
    body = dict(
        leaseId=claimed["leaseId"],
        actionId="probe",
        actionKey=key,
        parameterHash=parameters,
        beforeEvidence="evidence://before",
    )
    return task, auth, body


def paths(task, body):
    base = f"/companion/v2/tasks/{task}/actions"
    return base + "/intent", base + "/" + body["actionKey"]


def test_golden_identity():
    value = json.loads(
        (
            Path(__file__).resolve().parents[2] / "contracts/phase1/p09-action-identity-golden.json"
        ).read_text()
    )
    assert action_identity(
        *(
            value[k]
            for k in (
                "taskId",
                "commandType",
                "accountId",
                "bindingVersion",
                "snapshotSha256",
                "recipeSha256",
                "actionId",
            )
        )
    ) == (value["actionKey"], value["parameterHash"])


@pytest.mark.parametrize(
    "observed,decision",
    [
        ("APPLIED", "CONFIRMED_APPLIED"),
        ("UNKNOWN", "CONFIRMED_NOT_SUBMITTED"),
    ],
)
async def test_lost_response_outcome_and_explicit_resolution(api, observed, decision):  # noqa: F811
    client, app = api
    task, auth, body = await running(api)
    intent, action = paths(task, body)
    first = await client.post(intent, headers=auth, json=body)
    assert first.status_code == 201, first.text
    assert first.json()["decision"] == "AUTHORIZED"
    replay = await client.post(intent, headers=auth, json=body)
    assert replay.status_code == 200
    assert replay.json()["decision"] == "RECONCILE_REQUIRED"
    assert replay.json()["action"] == first.json()["action"]
    report = dict(
        leaseId=body["leaseId"],
        parameterHash=body["parameterHash"],
        status=observed,
        evidence="evidence://independent-after",
    )
    response = await client.post(action + "/outcome", headers=auth, json=report)
    assert response.status_code == 200, response.text
    assert response.json()["resolutionRevision"] == 0
    duplicate = await client.post(action + "/outcome", headers=auth, json=report)
    assert duplicate.json() == response.json()
    conflict = await client.post(
        action + "/outcome", headers=auth, json={**report, "evidence": "different"}
    )
    assert conflict.status_code == 409
    waiting = await client.post(
        f"/api/v1/platform-tasks/{task}:reconcile",
        headers=identity(),
        json={"decision": "KEEP_WAITING", "evidence": "inspect later"},
    )
    assert waiting.status_code == 200, waiting.text
    async with app.state.database.unit_of_work() as session:
        row = await session.get(MobileTaskRow, task)
        ledger = await session.get(MobileActionCommitRow, body["actionKey"])
        assert row.business_state == "RECONCILING"
        assert ledger.resolution_revision == 0
    if observed == "APPLIED":
        contradiction = await client.post(
            f"/api/v1/platform-tasks/{task}:reconcile",
            headers=identity(),
            json={"decision": "CONFIRMED_NOT_SUBMITTED", "evidence": "contradiction"},
        )
        assert contradiction.status_code == 409
        missing_item = await client.post(
            f"/api/v1/platform-tasks/{task}:reconcile",
            headers=identity(),
            json={"decision": decision, "evidence": "counter observation"},
        )
        assert missing_item.status_code == 409
    resolved = await client.post(
        f"/api/v1/platform-tasks/{task}:reconcile",
        headers=identity(),
        json={
            "decision": decision,
            "evidence": "operator observation",
            "platformItemId": "probe-counter-1",
        },
    )
    assert resolved.status_code == 200, resolved.text
    read = await client.get(action, headers=auth)
    assert read.status_code == 200
    assert read.json()["resolutionRevision"] == 1
    assert read.json()["resolutionEvidence"] == "operator observation"
    assert read.json()["status"] == ("APPLIED" if observed == "APPLIED" else "NOT_SUBMITTED")
    assert (await client.post(intent, headers=auth, json=body)).status_code == 409
    async with app.state.database.unit_of_work() as session:
        audit = list(
            await session.scalars(
                select(AuditEventRow).where(AuditEventRow.action.like("mobile.action.%"))
            )
        )
        assert len(audit) == 3
        assert audit[-1].metadata_json["resolutionRevision"] == 1


@pytest.mark.parametrize(
    "mutation", ["hash", "before", "snapshot", "pin", "binding", "lease", "action"]
)
async def test_frozen_identity_and_lease_fail_closed(api, mutation):  # noqa: F811
    client, app = api
    task, auth, body = await running(api)
    intent, action = paths(task, body)
    assert (await client.post(intent, headers=auth, json=body)).status_code == 201
    if mutation == "hash":
        body["parameterHash"] = "0" * 64
    elif mutation == "before":
        body["beforeEvidence"] = "changed"
    elif mutation == "lease":
        body["leaseId"] = "stale"
    elif mutation == "action":
        body["actionId"] = "absent"
    else:
        async with app.state.database.unit_of_work() as session:
            row = await session.get(MobileTaskRow, task)
            if mutation == "snapshot":
                row.command_payload = {**row.command_payload, "snapshotSha256": "0" * 64}
            elif mutation == "pin":
                row.recipe_pin = {**row.recipe_pin, "sha256": "0" * 64}
            else:
                row.binding_version += 1
    rejected = await client.post(intent, headers=auth, json=body)
    assert rejected.status_code == 409, rejected.text
    assert (await client.get(action, headers=auth)).json()["resolutionRevision"] == 0


async def test_expired_get_other_binding_and_postcondition(api):  # noqa: F811
    client, app = api
    task, auth, body = await running(api)
    intent, action = paths(task, body)
    assert (await client.post(intent, headers=auth, json=body)).status_code == 201
    report = dict(
        leaseId=body["leaseId"],
        parameterHash=body["parameterHash"],
        status="APPLIED",
        evidence=body["beforeEvidence"],
    )
    assert (await client.post(action + "/outcome", headers=auth, json=report)).status_code == 409
    other = await _enroll(
        client, await create_direct_device(client, "other-ledger"), "other-instance"
    )
    assert (await client.get(action, headers=other)).status_code == 404
    assert (await client.post(intent, headers=other, json=body)).status_code == 404
    assert (await client.post(action + "/outcome", headers=other, json=report)).status_code == 404
    async with app.state.database.unit_of_work() as session:
        row = await session.get(MobileTaskRow, task)
        row.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    assert (await client.post(intent, headers=auth, json=body)).status_code == 409
    assert (await client.post(action + "/outcome", headers=auth, json=report)).status_code == 409
    assert (await client.get(action, headers=auth)).status_code == 200


@pytest.mark.parametrize("mode", ["platform", "builtin", "app", "signature", "not_running"])
async def test_first_intent_scope_gate(api, mode):  # noqa: F811
    from cloudctl_api.db import AutomationVersionRow

    client, app = api
    task, auth, body = await running(api)
    intent, _ = paths(task, body)
    async with app.state.database.unit_of_work() as session:
        row = await session.get(MobileTaskRow, task)
        if mode == "platform":
            row.command_type = "xianyu.publish_listing.v1"
        elif mode == "builtin":
            row.recipe_pin = {"versionId": "builtin", "sha256": "a" * 64}
        elif mode == "app":
            row.target_package = "com.taobao.idlefish"
        elif mode == "not_running":
            row.business_state = "PAUSED_WAITING_USER"
        else:
            package = await session.get(AutomationVersionRow, row.recipe_pin["versionId"])
            package.manifest = {
                **package.manifest,
                "signature": {
                    **package.manifest["signature"],
                    "digest": "invalid",
                },
            }
    response = await client.post(intent, headers=auth, json=body)
    assert response.status_code == 409, response.text
    if mode in {"platform", "app"}:
        assert "G3_NOT_ACCEPTED" in response.text
    async with app.state.database.unit_of_work() as session:
        assert await session.get(MobileActionCommitRow, body["actionKey"]) is None
        assert (await session.get(MobileTaskRow, task)).business_state != "RECONCILING"


async def test_concurrent_first_grant_and_outcome(api):  # noqa: F811
    client, app = api
    if app.state.database.engine.dialect.name != "postgresql":
        pytest.skip("row-lock concurrency requires disposable PostgreSQL")
    task, auth, body = await running(api)
    intent, action = paths(task, body)
    responses = await asyncio.gather(
        *(client.post(intent, headers=auth, json=body) for _ in range(6))
    )
    assert sorted(r.status_code for r in responses) == [200, 200, 200, 200, 200, 201]
    assert sum(r.json()["decision"] == "AUTHORIZED" for r in responses) == 1
    reports = [
        dict(
            leaseId=body["leaseId"],
            parameterHash=body["parameterHash"],
            status=status,
            evidence=f"evidence://{status}",
        )
        for status in ("APPLIED", "UNKNOWN")
    ]
    responses = await asyncio.gather(
        *(client.post(action + "/outcome", headers=auth, json=b) for b in reports)
    )
    assert sorted(r.status_code for r in responses) == [200, 409]
