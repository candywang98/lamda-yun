"""X11 — per-target maintenance execution semantics against the control API.

Frozen task card X11 (fleet-first-20260916.1): maintenance actions execute
per target by identity. This file pins the SERVER side of that contract
against the existing batch entry (`POST /api/v1/xianyu/maintenance:run`) —
no service changes ship in this wave; the device-side pure-decision layer
lives in mobile companion `features/xianyu/maintenance/basic/`.

Pinned semantics:

- one controlled task per title target, each with its own gated confirm
  identity (a task-A action key never authorizes task B's confirm);
- a replayed run recreates nothing: per-target idempotency (completed
  actions are not re-executed);
- title-targeting guards each reject with their own message: duplicate
  titles (same-title ambiguity), blank/oversized titles, over the 50-target
  bound, mixed targeting modes, unbounded sweeps;
- outcome codes stay per action (polish/delist/delete), never one collapsed
  success/delete wire.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from cloudctl_api import create_app
from cloudctl_api.db import MobileTaskRow
from cloudctl_api.mobile_actions import steps_action_identity
from cloudctl_api.settings import Settings
from fastapi import FastAPI
from sqlalchemy import select
from test_platform_tasks import _enroll, create_direct_device, identity

XIANYU = "com.taobao.idlefish"


@pytest.fixture
async def api() -> AsyncIterator[tuple[httpx.AsyncClient, FastAPI]]:
    app = create_app(Settings(env="test", repository_mode="memory", dev_auth_bypass=True))
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, app


async def _run_maintenance(
    client: httpx.AsyncClient,
    device: str,
    key: str,
    body: dict[str, Any],
) -> httpx.Response:
    return await client.post(
        "/api/v1/xianyu/maintenance:run",
        headers={**identity(), "Idempotency-Key": key},
        json={"deviceId": device, **body},
    )


async def _frozen_identity(app: FastAPI, task_id: str) -> dict[str, Any]:
    async with app.state.database.unit_of_work() as session:
        row = await session.get(MobileTaskRow, task_id)
        assert row is not None
        return steps_action_identity(row)


async def _claim_and_heartbeat(
    client: httpx.AsyncClient, auth: dict[str, str], task_id: str
) -> dict[str, str]:
    claimed = await client.post(
        "/companion/v2/tasks/claim", headers=auth, json={"leaseSeconds": 60}
    )
    assert claimed.status_code == 200, claimed.text
    assert claimed.json()["taskId"] == task_id
    lease_id = claimed.json()["leaseId"]
    started = await client.post(
        f"/companion/v2/tasks/{task_id}/heartbeat",
        headers=auth,
        json={"leaseId": lease_id, "currentStep": 0},
    )
    assert started.status_code == 200, started.text
    return dict(leaseId=lease_id)


async def _settle_applied(
    client: httpx.AsyncClient,
    auth: dict[str, str],
    task_id: str,
    body: dict[str, Any],
    *,
    with_intent: bool = True,
) -> None:
    """Full gated cycle: intent 201 -> outcome APPLIED -> operator resolution."""
    if with_intent:
        intent = await client.post(
            f"/companion/v2/tasks/{task_id}/actions/intent", headers=auth, json=body
        )
        assert intent.status_code == 201, intent.text
    outcome = dict(
        leaseId=body["leaseId"],
        parameterHash=body["parameterHash"],
        status="APPLIED",
        evidence="sha256:" + "e" * 64,
    )
    action = f"/companion/v2/tasks/{task_id}/actions/{body['actionKey']}"
    reported = await client.post(action + "/outcome", headers=auth, json=outcome)
    assert reported.status_code == 200, reported.text
    resolved = await client.post(
        f"/api/v1/platform-tasks/{task_id}:reconcile",
        headers=identity(),
        json={
            "decision": "CONFIRMED_APPLIED",
            "evidence": "operator verified per-target badge evidence",
            "platformItemId": f"xianyu-targeting-{task_id[:8]}",
        },
    )
    assert resolved.status_code == 200, resolved.text


# ---------------------------------------------------------------------------
# Per-target gated identity (X11 core: every target approves independently)
# ---------------------------------------------------------------------------


async def test_each_title_target_carries_its_own_gated_identity(api):
    client, app = api
    device = await create_direct_device(client, "x11-identity")
    response = await _run_maintenance(
        client,
        device,
        "x11-identity-key",
        {
            "action": "delist",
            "path": "v2",
            "targets": {"titles": ["二战史-01", "二战史-02"]},
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["targetCount"] == 2
    first_id, second_id = body["taskIds"]
    assert first_id != second_id
    assert [task["title"] for task in body["tasks"]] == ["二战史-01", "二战史-02"]

    first_frozen = await _frozen_identity(app, first_id)
    second_frozen = await _frozen_identity(app, second_id)
    # Same frozen actionId (v1 lineage), DIFFERENT action key per target:
    # the gated confirm identity is per-target, never per-batch.
    assert first_frozen["action_id"] == second_frozen["action_id"] == "confirm-delist"
    assert first_frozen["action_key"] != second_frozen["action_key"]

    # Drive target 1 through its own gated cycle.
    auth = await _enroll(client, device, "x11-instance")
    lease1 = await _claim_and_heartbeat(client, auth, first_id)
    first_body = dict(
        leaseId=lease1["leaseId"],
        actionId=first_frozen["action_id"],
        actionKey=first_frozen["action_key"],
        parameterHash=first_frozen["parameter_hash"],
        beforeEvidence="evidence://x11-before-1",
    )
    granted = await client.post(
        f"/companion/v2/tasks/{first_id}/actions/intent", headers=auth, json=first_body
    )
    assert granted.status_code == 201, granted.text
    assert granted.json()["decision"] == "AUTHORIZED"
    await _settle_applied(client, auth, first_id, first_body, with_intent=False)

    # Target 2: its own lease, but target 1's action identity → 409 mismatch.
    # A spent confirm on one target must never authorize another target.
    lease2 = await _claim_and_heartbeat(client, auth, second_id)
    cross_body = dict(
        leaseId=lease2["leaseId"],
        actionId=first_frozen["action_id"],
        actionKey=first_frozen["action_key"],
        parameterHash=first_frozen["parameter_hash"],
        beforeEvidence="evidence://x11-before-2",
    )
    cross = await client.post(
        f"/companion/v2/tasks/{second_id}/actions/intent", headers=auth, json=cross_body
    )
    assert cross.status_code == 409, cross.text
    assert "action identity mismatch" in cross.text

    # With its OWN identity, target 2 authorizes independently.
    own_body = dict(
        leaseId=lease2["leaseId"],
        actionId=second_frozen["action_id"],
        actionKey=second_frozen["action_key"],
        parameterHash=second_frozen["parameter_hash"],
        beforeEvidence="evidence://x11-before-2",
    )
    own = await client.post(
        f"/companion/v2/tasks/{second_id}/actions/intent", headers=auth, json=own_body
    )
    assert own.status_code == 201, own.text
    assert own.json()["decision"] == "AUTHORIZED"


# ---------------------------------------------------------------------------
# Per-target idempotency: a replayed run recreates nothing
# ---------------------------------------------------------------------------


async def test_replayed_run_after_partial_completion_creates_no_new_tasks(api):
    client, app = api
    device = await create_direct_device(client, "x11-replay")
    first = await _run_maintenance(
        client,
        device,
        "x11-replay-key",
        {
            "action": "delist",
            "path": "v2",
            "targets": {"titles": ["二战史-01", "二战史-02"]},
        },
    )
    assert first.status_code == 201, first.text
    body = first.json()
    run_id = body["runId"]
    first_id, second_id = body["taskIds"]

    # Settle ONLY the first target to a terminal state (operator confirmed).
    frozen = await _frozen_identity(app, first_id)
    auth = await _enroll(client, device, "x11-replay-instance")
    lease = await _claim_and_heartbeat(client, auth, first_id)
    await _settle_applied(
        client,
        auth,
        first_id,
        dict(
            leaseId=lease["leaseId"],
            actionId=frozen["action_id"],
            actionKey=frozen["action_key"],
            parameterHash=frozen["parameter_hash"],
            beforeEvidence="evidence://x11-replay-1",
        ),
    )

    # Replay the same run key: same tasks, nothing re-created (200 replay).
    replay = await _run_maintenance(
        client,
        device,
        "x11-replay-key",
        {
            "action": "delist",
            "path": "v2",
            "targets": {"titles": ["二战史-01", "二战史-02"]},
        },
    )
    assert replay.status_code == 200, replay.text
    assert replay.headers["Idempotency-Replayed"] == "true"
    assert replay.json()["taskIds"] == body["taskIds"]

    async with app.state.database.unit_of_work() as session:
        rows = list(
            await session.scalars(select(MobileTaskRow).where(MobileTaskRow.batch_id == run_id))
        )
    assert len(rows) == 2  # no third task appeared

    # Summary keeps per-target states independent: one terminal, one not.
    summary = await client.get(f"/api/v1/xianyu/maintenance/runs/{run_id}", headers=identity())
    assert summary.status_code == 200, summary.text
    payload = summary.json()
    assert payload["taskCount"] == 2
    states = {task["taskId"]: task["state"] for task in payload["tasks"]}
    assert states[first_id] == "SUCCEEDED"
    assert states[second_id] != "SUCCEEDED"
    assert payload["allTerminal"] is False


# ---------------------------------------------------------------------------
# Targeting guards: each rejection carries its own message
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("mutation", "marker"),
    [
        # Same-title ambiguity: two identical titles would make the device
        # locator match 2 cards — rejected server-side, never auto-picked.
        ("duplicate_titles", "titles must be unique"),
        ("blank_title", "titles entries must contain 1 to 64 characters"),
        ("oversized_title", "titles entries must contain 1 to 64 characters"),
        # Target-count bound mirrors the device-side TARGET_COUNT_LIMIT stop.
        ("fifty_one_titles", "at most 50"),
        # Mixed targeting modes are contradictory plans — rejected.
        ("titles_plus_card_indices", "titles only; card coordinates do not apply"),
        ("v2_without_titles", "the v2 title path requires targets.titles"),
        ("polish_with_titles", "polish takes no v2 path"),
        # Unbounded sweeps are refused: the server cannot read the on-device
        # badge count, so targets.all must stay explicitly bounded.
        ("all_without_limit", "requires cardLimit"),
        ("delist_second_card", "only the first on-sale card (index 0)"),
        ("delist_limit_two", "cardLimit 1"),
    ],
)
async def test_targeting_guards_reject_with_distinct_markers(api, mutation, marker):
    client, _ = api
    device = await create_direct_device(client, f"x11-guard-{mutation[:16]}")
    body: dict[str, Any] = {"action": "delist", "path": "v2", "targets": {"titles": ["二战史-01"]}}
    if mutation == "duplicate_titles":
        body["targets"] = {"titles": ["二战史-01", "二战史-01"]}
    elif mutation == "blank_title":
        body["targets"] = {"titles": [""]}
    elif mutation == "oversized_title":
        body["targets"] = {"titles": ["长" * 65]}
    elif mutation == "fifty_one_titles":
        body["targets"] = {"titles": [f"标题-{index:02d}" for index in range(51)]}
    elif mutation == "titles_plus_card_indices":
        body["targets"] = {"titles": ["二战史-01"], "cardIndices": [0]}
    elif mutation == "v2_without_titles":
        body["targets"] = {}
    elif mutation == "polish_with_titles":
        body = {"action": "polish", "path": "v2", "targets": {"titles": ["二战史-01"]}}
    elif mutation == "all_without_limit":
        body = {"action": "delete", "path": "v1", "targets": {"all": True}}
    elif mutation == "delist_second_card":
        body = {"action": "delist", "path": "v1", "targets": {"cardIndices": [1]}}
    elif mutation == "delist_limit_two":
        body = {"action": "delist", "path": "v1", "targets": {"all": True, "cardLimit": 2}}
    response = await _run_maintenance(client, device, f"x11-guard-{mutation}", body)
    assert response.status_code == 422, response.text
    assert marker in response.text, response.text


# ---------------------------------------------------------------------------
# Outcome codes stay per action (never one collapsed success/delete wire)
# ---------------------------------------------------------------------------


async def test_outcome_codes_stay_independent_per_action(api):
    client, app = api
    expectations = [
        ("polish", "v1", "xianyu.polish.steps.v1", "XIANYU_POLISH_DONE"),
        ("delist", "v2", "xianyu.delist.steps.v2", "XIANYU_DELIST_DONE"),
        ("delete", "v2", "xianyu.delete_delisted.steps.v2", "XIANYU_DELETE_DELISTED_DONE"),
    ]
    seen_codes: set[str] = set()
    for action, path, command_type, message_code in expectations:
        device = await create_direct_device(client, f"x11-outcome-{action}")
        targets: dict[str, Any] = {} if action == "polish" else {"titles": ["二战史-01"]}
        response = await _run_maintenance(
            client,
            device,
            f"x11-outcome-{action}",
            {"action": action, "path": path, "targets": targets},
        )
        assert response.status_code == 201, response.text
        assert response.json()["commandType"] == command_type
        task_id = response.json()["taskIds"][0]
        async with app.state.database.unit_of_work() as session:
            row = await session.get(MobileTaskRow, task_id)
            assert row is not None
            logs = [step for step in row.steps if step.get("action") == "run.log"]
        assert [log["messageCode"] for log in logs] == [message_code]
        seen_codes.add(message_code)
    # Three actions, three distinct done codes: no unified success marker.
    assert len(seen_codes) == 3
