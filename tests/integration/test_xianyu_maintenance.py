"""Xianyu maintenance shapes and batch orchestration.

Frozen against contracts/phase1/xianyu-maintenance-anchors-20260915.md:
polish (light risk, no ledger click), delist and delete-delisted (one
ledger-gated confirm tap each, post-badge verification, screenshot evidence).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx
import pytest
from cloudctl_api import create_app
from cloudctl_api.db import MobileActionCommitRow, MobileTaskRow
from cloudctl_api.mobile_actions import steps_action_identity, validate_maintenance_steps
from cloudctl_api.settings import Settings
from cloudctl_domain import ConflictError
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



def tab_for(ref: str) -> str:
    return "delisted" if ref in ("delete_card", "confirm_delete") else "onsale"

def _tap(step_id: str, ref: str) -> dict[str, Any]:
    return {"stepId": step_id, "action": "ui.tap", "locatorRef": ref, "timeoutMs": 8_000}


def _layout(step_id: str, ref: str, card_index: int | None = None) -> dict[str, Any]:
    return {
        "stepId": step_id,
        "action": "ui.tapLayout",
        "layoutAction": ref,
        "tab": tab_for(ref),
        "cardIndex": card_index or 0,
        "timeoutMs": 10_000,
    }


def _shot(label: str) -> dict[str, Any]:
    return {
        "stepId": f"capture-{label}",
        "action": "ui.screenshot",
        "label": label,
        "timeoutMs": 10_000,
    }


def _badge(tab: str) -> dict[str, Any]:
    return {
        "stepId": f"assert-{tab}",
        "action": "ui.assertBadge",
        "locatorRef": "xianyu_pub_tab_onsale" if tab == "onsale" else "xianyu_pub_tab_delisted",
        "expectedDelta": -1,
        "timeoutMs": 15_000,
    }


def _log(code: str) -> dict[str, Any]:
    return {
        "stepId": "mark-done",
        "action": "run.log",
        "level": "INFO",
        "messageCode": code,
        "timeoutMs": 1_000,
    }


def polish_steps() -> list[dict[str, Any]]:
    return [
        _tap("open-profile", "xianyu_profile_tab"),
        _tap("open-my-published", "xianyu_my_published"),
        _layout("tap-polish-all", "polish_all"),
        _shot("xianyu_polish_all"),
        _log("XIANYU_POLISH_DONE"),
    ]


def delist_steps(card_index: int = 0) -> list[dict[str, Any]]:
    return [
        _tap("open-profile", "xianyu_profile_tab"),
        _tap("open-my-published", "xianyu_my_published"),
        _layout("open-card-menu", "more", card_index),
        _shot("xianyu_delist_menu"),
        _layout("tap-delist-item", "delist_menu_item"),
        _shot("xianyu_delist_confirm"),
        _layout("confirm-delist", "confirm_delist"),
        _badge("onsale"),
        _shot("xianyu_delist_result"),
        _log("XIANYU_DELIST_DONE"),
    ]


def delete_steps(card_index: int = 0) -> list[dict[str, Any]]:
    return [
        _tap("open-profile", "xianyu_profile_tab"),
        _tap("open-my-published", "xianyu_my_published"),
        _tap("open-delisted-tab", "xianyu_pub_tab_delisted"),
        _layout("tap-delete-card", "delete_card", card_index),
        _shot("xianyu_delete_confirm"),
        _layout("confirm-delete", "confirm_delete"),
        _badge("delisted"),
        _shot("xianyu_delete_result"),
        _log("XIANYU_DELETE_DELISTED_DONE"),
    ]


def _drop(steps: list[dict[str, Any]], *, step_id: str) -> list[dict[str, Any]]:
    return [step for step in steps if step["stepId"] != step_id]


async def _create_steps_task(
    client: httpx.AsyncClient, device: str, steps: list[dict[str, Any]], key: str
) -> httpx.Response:
    return await client.post(
        "/api/v1/mobile/tasks",
        headers={**identity(), "Idempotency-Key": key},
        json={
            "deviceId": device,
            "targetPackage": XIANYU,
            "totalTimeoutMs": 120_000,
            "steps": steps,
        },
    )


async def _start_task(
    client: httpx.AsyncClient,
    app: FastAPI,
    device: str,
    steps: list[dict[str, Any]],
    key: str,
    instance: str,
    *,
    with_identity: bool = True,
) -> tuple[str, dict[str, str], dict[str, Any]]:
    """Create, claim and start a steps task; return ids and frozen identity.

    A device has one active runner, so callers must settle a running task
    before starting the next one on the same device.
    """

    created = await _create_steps_task(client, device, steps, key)
    assert created.status_code == 201, created.text
    task_id = created.json()["taskId"]
    auth = await _enroll(client, device, instance)
    claimed = await client.post(
        "/companion/v2/tasks/claim", headers=auth, json={"leaseSeconds": 60}
    )
    assert claimed.status_code == 200, claimed.text
    assert claimed.json()["taskId"] == task_id
    started = await client.post(
        f"/companion/v2/tasks/{task_id}/heartbeat",
        headers=auth,
        json={"leaseId": claimed.json()["leaseId"], "currentStep": 0},
    )
    assert started.status_code == 200, started.text
    lease_id = claimed.json()["leaseId"]
    if not with_identity:
        return task_id, auth, dict(leaseId=lease_id)
    async with app.state.database.unit_of_work() as session:
        row = await session.get(MobileTaskRow, task_id)
        frozen = steps_action_identity(row)
    return task_id, auth, dict(
        leaseId=lease_id,
        actionId=frozen["action_id"],
        actionKey=frozen["action_key"],
        parameterHash=frozen["parameter_hash"],
        beforeEvidence="evidence://maintenance-before",
    )


async def _authorize_and_resolve(
    client: httpx.AsyncClient, task_id: str, auth: dict[str, str], body: dict[str, Any]
) -> None:
    """Full gated cycle: intent 201 -> outcome APPLIED -> operator resolution."""
    intent = f"/companion/v2/tasks/{task_id}/actions/intent"
    granted = await client.post(intent, headers=auth, json=body)
    assert granted.status_code == 201, granted.text
    outcome = dict(
        leaseId=body["leaseId"],
        parameterHash=body["parameterHash"],
        status="APPLIED",
        evidence="sha256:" + "c" * 64,
    )
    action = f"/companion/v2/tasks/{task_id}/actions/{body['actionKey']}"
    reported = await client.post(action + "/outcome", headers=auth, json=outcome)
    assert reported.status_code == 200, reported.text
    resolved = await client.post(
        f"/api/v1/platform-tasks/{task_id}:reconcile",
        headers=identity(),
        json={
            "decision": "CONFIRMED_APPLIED",
            "evidence": "operator verified badge evidence",
            "platformItemId": f"xianyu-maintenance-{task_id[:8]}",
        },
    )
    assert resolved.status_code == 200, resolved.text


# --------------------------------------------------------------------------
# Shape validation at task creation (422 gate)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "build,command",
    [
        (polish_steps, "xianyu.polish.steps.v1"),
        (delist_steps, "xianyu.delist.steps.v1"),
        (delete_steps, "xianyu.delete_delisted.steps.v1"),
    ],
)
async def test_valid_maintenance_shapes_are_accepted(api, build, command):
    client, _ = api
    device = await create_direct_device(client, f"shape-{command.split('.')[1][:8]}")
    steps = build()
    response = await _create_steps_task(client, device, steps, f"shape-{device[:12]}")
    assert response.status_code == 201, response.text
    assert validate_maintenance_steps(XIANYU, steps) == command


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_gated",
        "missing_badge",
        "missing_screenshot",
        "gated_twice",
        "missing_delisted_tab",
        "wrong_badge_tab",
    ],
)
async def test_destructive_shape_violations_are_rejected(api, mutation):
    client, _ = api
    steps = delete_steps() if mutation == "missing_delisted_tab" else delist_steps()
    if mutation == "missing_gated":
        steps = _drop(steps, step_id="confirm-delist")
    elif mutation == "missing_badge":
        steps = _drop(steps, step_id="assert-onsale")
    elif mutation == "missing_screenshot":
        steps = _drop(steps, step_id="capture-xianyu_delist_result")
    elif mutation == "gated_twice":
        gated = next(step for step in steps if step["stepId"] == "confirm-delist")
        steps = [*steps, {**gated, "stepId": "confirm-delist-again"}]
    elif mutation == "missing_delisted_tab":
        steps = _drop(steps, step_id="open-delisted-tab")
    else:  # wrong_badge_tab
        steps = [
            dict(step, tab="delisted") if step["action"] == "ui.assertBadge" else step
            for step in steps
        ]
    device = await create_direct_device(client, f"bad-{mutation}")
    response = await _create_steps_task(client, device, steps, f"bad-{mutation}-{device[:8]}")
    assert response.status_code == 422, response.text
    assert "frozen command shape" in response.text or "Extra inputs" in response.text


@pytest.mark.parametrize(
    "steps_factory",
    [
        # polish without the mandatory screenshot evidence
        lambda: _drop(polish_steps(), step_id="capture-xianyu_polish_all"),
        # polish must stay light-risk: badge assertions do not belong to it
        lambda: [*polish_steps(), _badge("onsale")],
        # unapproved layout region
        lambda: [
            *_drop(polish_steps(), step_id="tap-polish-all"),
            _layout("tap-x", "relist_button"),
        ],
    ],
)
async def test_polish_shape_edge_rejections(api, steps_factory: Callable[[], list[dict[str, Any]]]):
    client, _ = api
    device = await create_direct_device(client, "polish-edges")
    response = await _create_steps_task(
        client, device, steps_factory(), f"polish-edge-{device[:8]}"
    )
    assert response.status_code == 422, response.text


async def test_card_index_out_of_range_is_rejected(api):
    client, _ = api
    device = await create_direct_device(client, "card-range")
    response = await _create_steps_task(
        client, device, delist_steps(card_index=50), f"card-range-{device[:8]}"
    )
    assert response.status_code == 422, response.text


# --------------------------------------------------------------------------
# GATED ledger semantics (P09 controlled action ledger)
# --------------------------------------------------------------------------


async def test_delist_gated_intent_authorized_once_then_locked(api):
    client, app = api
    device = await create_direct_device(client, "ledger-delist")
    task_id, auth, body = await _start_task(
        client, app, device, delist_steps(0), "ledger-delist-key", "ledger-delist-instance"
    )
    assert body["actionId"] == "confirm-delist"
    intent = f"/companion/v2/tasks/{task_id}/actions/intent"
    first = await client.post(intent, headers=auth, json=body)
    assert first.status_code == 201, first.text
    assert first.json()["decision"] == "AUTHORIZED"
    assert first.json()["action"]["actionId"] == "confirm-delist"
    # Exact duplicate replay never grants a second authorization.
    replay = await client.post(intent, headers=auth, json=body)
    assert replay.status_code == 200
    assert replay.json()["decision"] == "RECONCILE_REQUIRED"
    # A foreign action id is refused outright.
    wrong = await client.post(
        intent, headers=auth, json={**body, "actionId": "click-publish"}
    )
    assert wrong.status_code == 409
    outcome = dict(
        leaseId=body["leaseId"],
        parameterHash=body["parameterHash"],
        status="APPLIED",
        evidence="sha256:" + "b" * 64,
    )
    action = f"/companion/v2/tasks/{task_id}/actions/{body['actionKey']}"
    reported = await client.post(action + "/outcome", headers=auth, json=outcome)
    assert reported.status_code == 200, reported.text
    resolved = await client.post(
        f"/api/v1/platform-tasks/{task_id}:reconcile",
        headers=identity(),
        json={
            "decision": "CONFIRMED_APPLIED",
            "evidence": "onsale badge decreased by one",
            "platformItemId": "xianyu-listing-delist-0",
        },
    )
    assert resolved.status_code == 200, resolved.text
    # The resolved action key is never executable again (UNKNOWN never retried).
    again = await client.post(intent, headers=auth, json=body)
    assert again.status_code == 409


async def test_each_target_has_an_independent_gated_identity(api):
    client, app = api
    device = await create_direct_device(client, "cross-task")
    # One active runner per device: settle card 0 before starting card 1.
    task0, auth0, body0 = await _start_task(
        client, app, device, delete_steps(0), "cross-task-0", "cross-instance"
    )
    await _authorize_and_resolve(client, task0, auth0, body0)
    task1, auth1, body1 = await _start_task(
        client, app, device, delete_steps(1), "cross-task-1", "cross-instance"
    )
    assert body0["actionKey"] != body1["actionKey"]
    assert body0["parameterHash"] != body1["parameterHash"]
    # Both gated confirms were authorized independently (two distinct identities).
    response = await client.post(
        f"/companion/v2/tasks/{task1}/actions/intent", headers=auth1, json=body1
    )
    assert response.status_code == 201, response.text
    async with app.state.database.unit_of_work() as session:
        keys = list(
            await session.scalars(
                select(MobileActionCommitRow.action_key).where(
                    MobileActionCommitRow.task_id.in_([task0, task1])
                )
            )
        )
        assert len(keys) == 2


async def test_polish_has_no_ledger_click_and_is_refused(api):
    client, app = api
    device = await create_direct_device(client, "ledger-polish")
    task_id, auth, body = await _start_task(
        client,
        app,
        device,
        polish_steps(),
        "ledger-polish-key",
        "ledger-polish-instance",
        with_identity=False,
    )
    response = await client.post(
        f"/companion/v2/tasks/{task_id}/actions/intent",
        headers=auth,
        json=dict(
            leaseId=body["leaseId"],
            actionId="tap-polish-all",
            actionKey="a" * 64,
            parameterHash="b" * 64,
            beforeEvidence="evidence://x",
        ),
    )
    assert response.status_code == 409
    assert "G3_NOT_ACCEPTED" in response.text
    async with app.state.database.unit_of_work() as session:
        rows = list(
            await session.scalars(
                select(MobileActionCommitRow).where(MobileActionCommitRow.task_id == task_id)
            )
        )
        assert rows == []


async def test_mutated_shape_cannot_request_intent(api):
    client, app = api
    device = await create_direct_device(client, "mutated")
    task_id, auth, body = await _start_task(
        client, app, device, delete_steps(2), "mutated-key", "mutated-instance"
    )
    async with app.state.database.unit_of_work() as session:
        row = await session.get(MobileTaskRow, task_id, with_for_update=True)
        header, *steps = row.steps
        row.steps = [
            header,
            *[step for step in steps if step.get("layoutAction") != "confirm_delete"],
        ]
        with pytest.raises(ConflictError):
            steps_action_identity(row)
    response = await client.post(
        f"/companion/v2/tasks/{task_id}/actions/intent", headers=auth, json=body
    )
    assert response.status_code == 409
    assert "G3_NOT_ACCEPTED" in response.text


# --------------------------------------------------------------------------
# Batch orchestration API
# --------------------------------------------------------------------------


async def _run(
    client: httpx.AsyncClient,
    device: str,
    action: str,
    targets: dict[str, Any],
    key: str,
    *,
    role: str = "device_operator",
) -> httpx.Response:
    return await client.post(
        "/api/v1/xianyu/maintenance:run",
        headers={**identity(role=role), "Idempotency-Key": key},
        json={"deviceId": device, "action": action, "targets": targets},
    )


async def test_run_permission_matrix(api):
    client, _ = api
    device = await create_direct_device(client, "perm")
    denied = await _run(client, device, "polish", {}, "perm-viewer", role="viewer")
    assert denied.status_code == 403, denied.text
    allowed = await _run(client, device, "polish", {}, "perm-operator")
    assert allowed.status_code == 201, allowed.text


async def test_run_batch_is_idempotent_and_queryable(api):
    client, app = api
    device = await create_direct_device(client, "batch")
    first = await _run(client, device, "delete", {"cardIndices": [2, 0]}, "batch-key")
    assert first.status_code == 201, first.text
    body = first.json()
    assert body["action"] == "delete"
    assert body["commandType"] == "xianyu.delete_delisted.steps.v1"
    assert body["targetCount"] == 2
    assert [task["cardIndex"] for task in body["tasks"]] == [0, 2]
    run_id = body["runId"]

    replay = await _run(client, device, "delete", {"cardIndices": [2, 0]}, "batch-key")
    assert replay.status_code == 200
    assert replay.headers["Idempotency-Replayed"] == "true"
    assert replay.json()["taskIds"] == body["taskIds"]
    async with app.state.database.unit_of_work() as session:
        rows = list(
            await session.scalars(
                select(MobileTaskRow).where(MobileTaskRow.batch_id == run_id)
            )
        )
        assert len(rows) == 2
        assert all(row.idempotency_key.startswith("maintenance-delete-") for row in rows)

    summary = await client.get(
        f"/api/v1/xianyu/maintenance/runs/{run_id}", headers=identity()
    )
    assert summary.status_code == 200, summary.text
    payload = summary.json()
    assert payload["taskCount"] == 2
    assert payload["summary"] == {"QUEUED": 2}
    assert payload["allTerminal"] is False
    assert {task["cardIndex"] for task in payload["tasks"]} == {0, 2}

    # The companion claims a controlled steps task and sees exactly one gated tap.
    auth = await _enroll(client, device, "batch-instance")
    claimed = await client.post(
        "/companion/v2/tasks/claim", headers=auth, json={"leaseSeconds": 60}
    )
    assert claimed.status_code == 200, claimed.text
    gated = [
        step for step in claimed.json()["steps"] if step.get("layoutAction") == "confirm_delete"
    ]
    assert len(gated) == 1
    assert claimed.json()["targetPackage"] == XIANYU
    # The companion gates the destructive confirm on the claimed payload carrying
    # the maintenance commandType (identity construction rejects a null).
    assert claimed.json()["commandType"] == "xianyu.delete_delisted.steps.v1"

    missing = await client.get(
        "/api/v1/xianyu/maintenance/runs/00000000-0000-0000-0000-000000000000",
        headers=identity(),
    )
    assert missing.status_code == 404
    viewer = await client.get(
        f"/api/v1/xianyu/maintenance/runs/{run_id}", headers=identity(role="viewer")
    )
    assert viewer.status_code == 200


async def test_polish_run_creates_single_task(api):
    client, _ = api
    device = await create_direct_device(client, "polish-run")
    response = await _run(client, device, "polish", {}, "polish-key")
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["targetCount"] == 1
    assert body["tasks"][0]["commandType"] == "xianyu.polish.steps.v1"
    assert body["tasks"][0]["cardIndex"] is None
    with_targets = await _run(client, device, "polish", {"cardIndices": [0]}, "polish-targets")
    assert with_targets.status_code == 422


async def test_delete_all_uses_bounded_card_limit(api):
    client, _ = api
    device = await create_direct_device(client, "delete-all")
    response = await _run(
        client, device, "delete", {"all": True, "cardLimit": 3}, "delete-all-key"
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert [task["cardIndex"] for task in body["tasks"]] == [0, 1, 2]
    assert body["tasks"][0]["commandType"] == "xianyu.delete_delisted.steps.v1"


@pytest.mark.parametrize(
    "targets",
    [
        {"titleContains": "券"},
        {"all": True},
        {"all": True, "cardIndices": [0], "cardLimit": 2},
        {},
        {"cardIndices": [50]},
    ],
)
async def test_invalid_targets_are_rejected(api, targets):
    client, _ = api
    device = await create_direct_device(client, "invalid-targets")
    response = await _run(client, device, "delist", targets, "invalid-targets")
    assert response.status_code == 422, response.text


async def test_run_requires_known_device_and_idempotency_key(api):
    client, _ = api
    unknown = await _run(
        client,
        "00000000-0000-0000-0000-000000000009",
        "delist",
        {"cardIndices": [0]},
        "unknown-device",
    )
    assert unknown.status_code == 404
    device = await create_direct_device(client, "no-key")
    response = await client.post(
        "/api/v1/xianyu/maintenance:run",
        headers=identity(),
        json={"deviceId": device, "action": "polish", "targets": {}},
    )
    assert response.status_code == 422, response.text
