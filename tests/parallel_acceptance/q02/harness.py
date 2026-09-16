"""Q02 harness: create a controlled steps task, claim it, and freeze identity.

Mirrors the production companion flow against the real HTTP API:
create (operator) -> claim (companion lease) -> heartbeat (RUNNING) ->
frozen ``steps_action_identity`` for the ledger-gated action.
"""

from __future__ import annotations

import uuid
from typing import Any

import httpx
from cloudctl_api.db import DeviceRow, MobileTaskRow
from cloudctl_api.mobile_actions import steps_action_identity
from fastapi import FastAPI

from .conftest import bind, claim, create_account, create_direct_device, enroll, identity

# Frozen publish shape (contract anchors shared with the companion; the same
# shape family is used by tests/integration/test_p09_action_ledger.py).
PUBLISH_STEPS = [
    {
        "stepId": "find-home-sell",
        "locatorRef": "xianyu_home_sell",
        "timeoutMs": 8000,
        "action": "ui.find",
    },
    {
        "stepId": "fill-description",
        "locatorRef": "xianyu_description",
        "timeoutMs": 20000,
        "action": "ui.input",
        "value": "Notion Business 兑换券，图示价值 $240。拍下后按说明发送兑换方式。支持当面交易。",
        "replace": True,
        "sensitive": False,
    },
    {
        "stepId": "wait-publish-button",
        "locatorRef": "xianyu_publish_button",
        "timeoutMs": 8000,
        "action": "ui.wait",
        "condition": "EXISTS",
        "pollMs": 200,
    },
    {
        "stepId": "click-publish",
        "locatorRef": "xianyu_publish_button",
        "timeoutMs": 5000,
        "action": "ui.tap",
    },
    {
        "stepId": "wait-publish-complete",
        "locatorRef": "xianyu_publish_success",
        "timeoutMs": 15000,
        "action": "ui.wait",
        "condition": "EXISTS",
        "pollMs": 500,
    },
]

_SEQUENCE = 0


def _next_suffix(prefix: str) -> str:
    global _SEQUENCE
    _SEQUENCE += 1
    return f"{prefix}-{_SEQUENCE}"


async def running_steps_task(
    api: tuple[httpx.AsyncClient, FastAPI],
    *,
    steps: list[dict[str, Any]] | None = None,
    with_heartbeat: bool = True,
) -> dict[str, Any]:
    """Create + claim (+ start) a controlled steps task; return full context."""
    client, app = api
    suffix = _next_suffix("q02")
    device_id = await create_direct_device(client, f"phone-{suffix}")
    account_id = await create_account(client, f"xy-{suffix}")
    await bind(client, account_id, device_id)
    created = await client.post(
        "/api/v1/mobile/tasks",
        headers={**identity(), "Idempotency-Key": f"q02-{uuid.uuid4().hex[:16]}"},
        json={
            "deviceId": device_id,
            "targetPackage": "com.taobao.idlefish",
            "totalTimeoutMs": 120_000,
            "steps": steps if steps is not None else PUBLISH_STEPS,
        },
    )
    assert created.status_code == 201, created.text
    task_id = created.json()["taskId"]
    auth = await enroll(client, device_id, f"instance-{suffix}")
    claimed = await claim(client, auth)
    assert claimed["taskId"] == task_id
    heartbeat: dict[str, Any] | None = None
    if with_heartbeat:
        started = await client.post(
            f"/companion/v2/tasks/{task_id}/heartbeat",
            headers=auth,
            json={"leaseId": claimed["leaseId"], "currentStep": 0, "leaseSeconds": 60},
        )
        assert started.status_code == 200, started.text
        heartbeat = started.json()
    async with app.state.database.unit_of_work() as session:
        row = await session.get(MobileTaskRow, task_id)
        assert row is not None
        frozen = steps_action_identity(row)
    return {
        "taskId": task_id,
        "deviceId": device_id,
        "accountId": account_id,
        "auth": auth,
        "leaseId": claimed["leaseId"],
        "claimed": claimed,
        "heartbeat": heartbeat,
        "frozen": frozen,
    }


def intent_body(ctx: dict[str, Any], before_evidence: str) -> dict[str, Any]:
    frozen = ctx["frozen"]
    return {
        "leaseId": ctx["leaseId"],
        "actionId": frozen["action_id"],
        "actionKey": frozen["action_key"],
        "parameterHash": frozen["parameter_hash"],
        "beforeEvidence": before_evidence,
    }


def action_paths(ctx: dict[str, Any]) -> tuple[str, str]:
    base = f"/companion/v2/tasks/{ctx['taskId']}/actions"
    return base + "/intent", base + "/" + ctx["frozen"]["action_key"]


async def post_event(
    client: httpx.AsyncClient,
    ctx: dict[str, Any],
    sequence: int,
    event_type: str,
    payload: dict[str, Any],
    step_index: int = 0,
    lease_id: str | None = None,
) -> httpx.Response:
    return await client.post(
        f"/companion/v2/tasks/{ctx['taskId']}/events",
        headers=ctx["auth"],
        json={
            "leaseId": lease_id or ctx["leaseId"],
            "sequence": sequence,
            "eventType": event_type,
            "stepIndex": step_index,
            "payload": payload,
        },
    )


async def device_counters(app: FastAPI, device_id: str) -> tuple[int, int]:
    async with app.state.database.unit_of_work() as session:
        device = await session.get(DeviceRow, device_id)
        assert device is not None
        return int(device.fencing_counter or 0), int(getattr(device, "control_epoch", 0) or 0)


async def expire_lease(app: FastAPI, task_id: str) -> None:
    """Force-expire the task lease to simulate companion loss before re-claim."""
    from datetime import UTC, datetime, timedelta

    async with app.state.database.unit_of_work() as session:
        row = await session.get(MobileTaskRow, task_id)
        assert row is not None
        row.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
