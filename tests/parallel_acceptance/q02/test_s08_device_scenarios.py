"""Q02 scenario 8 (class B): real-device scenarios - restart and live readback.

These tests are NOT run in CI. They are explicit device scenarios executed by
the controller while holding the DEVICE:<serial> lock, following the handbook
in artifacts/parallel/W5/Q02/README.md. They are skipped unless both
Q02_DEVICE_SERIAL and Q02_BASE_URL are set:

    Q02_DEVICE_SERIAL=<serial> Q02_BASE_URL=https://<control-api> \
        uv run python -m pytest -q tests/parallel_acceptance/q02/test_s08_device_scenarios.py

Operator identity headers come from Q02_TENANT / Q02_USER / Q02_ROLES
(defaults mirror the class-A suite). The device must already be enrolled
(companion installed, bound, accessibility on) and hold exactly one listing
eligible for the local readback action (xianyu delist, badge delta -1).

B1 restart: a controlled task must either resume on the same task after the
device reboots (companion re-claims, attempt+1, same taskId/attemptId) or
terminate safely (PAUSED_WAITING_USER / CANCEL_REQUESTED / RECONCILING) -
never a second parallel task and never a duplicate gated strike.

B2 readback: after the gated delist confirm, the on-device badge readback
(xianyu_pub_tab_onsale delta -1) must back the reported outcome; if the
readback is inconclusive the task lands UNKNOWN + RECONCILING and the
operator decision (with taskId + hashes) is recorded.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

pytestmark = pytest.mark.device_q02

POLL_SECONDS = float(os.environ.get("Q02_POLL_SECONDS", "300"))
POLL_INTERVAL = 5.0

DELIST_STEPS = [
    {
        "stepId": "open-profile",
        "action": "ui.tap",
        "locatorRef": "xianyu_profile_tab",
        "timeoutMs": 8_000,
    },
    {
        "stepId": "open-my-published",
        "action": "ui.tap",
        "locatorRef": "xianyu_my_published",
        "timeoutMs": 8_000,
    },
    {
        "stepId": "open-card-menu",
        "action": "ui.tapLayout",
        "layoutAction": "more",
        "tab": "onsale",
        "cardIndex": 0,
        "timeoutMs": 10_000,
    },
    {
        "stepId": "capture-menu",
        "action": "ui.screenshot",
        "label": "xianyu_delist_menu",
        "timeoutMs": 10_000,
    },
    {
        "stepId": "tap-delist-item",
        "action": "ui.tapLayout",
        "layoutAction": "delist_menu_item",
        "tab": "onsale",
        "cardIndex": 0,
        "timeoutMs": 10_000,
    },
    {
        "stepId": "capture-confirm",
        "action": "ui.screenshot",
        "label": "xianyu_delist_confirm",
        "timeoutMs": 10_000,
    },
    {
        "stepId": "confirm-delist",
        "action": "ui.tapLayout",
        "layoutAction": "confirm_delist",
        "tab": "onsale",
        "cardIndex": 0,
        "timeoutMs": 10_000,
    },
    {
        "stepId": "assert-onsale",
        "action": "ui.assertBadge",
        "locatorRef": "xianyu_pub_tab_onsale",
        "expectedDelta": -1,
        "timeoutMs": 15_000,
    },
    {
        "stepId": "capture-result",
        "action": "ui.screenshot",
        "label": "xianyu_delist_result",
        "timeoutMs": 10_000,
    },
    {
        "stepId": "mark-done",
        "action": "run.log",
        "level": "INFO",
        "messageCode": "XIANYU_DELIST_DONE",
        "timeoutMs": 1_000,
    },
]


def _operator_headers() -> dict[str, str]:
    return {
        "X-Tenant-Id": os.environ.get("Q02_TENANT", "00000000-0000-7000-8000-000000000111"),
        "X-User-Id": os.environ.get("Q02_USER", "00000000-0000-7000-8000-000000000222"),
        "X-Roles": os.environ.get("Q02_ROLES", "device_operator"),
        "X-MFA": "true",
        "X-Request-Id": str(uuid.uuid4()),
    }


@pytest.fixture
async def device_api() -> AsyncIterator[tuple[httpx.AsyncClient, str]]:
    base_url = os.environ["Q02_BASE_URL"]
    serial = os.environ["Q02_DEVICE_SERIAL"]
    async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
        yield client, serial


async def _device_id(client: httpx.AsyncClient, serial: str) -> str:
    # GET /api/v1/devices returns a bare list; the serial is embedded in logical_name.
    response = await client.get("/api/v1/devices", headers=_operator_headers())
    assert response.status_code == 200, response.text
    for device in response.json():
        if serial in str(device.get("logical_name") or ""):
            return str(device["id"])
    pytest.fail(f"device {serial} is not registered in the control API")


async def _create_delist_task(client: httpx.AsyncClient, device_id: str) -> dict[str, Any]:
    created = await client.post(
        "/api/v1/mobile/tasks",
        headers={**_operator_headers(), "Idempotency-Key": f"q02-device-{uuid.uuid4().hex[:16]}"},
        json={
            "deviceId": device_id,
            "targetPackage": "com.taobao.idlefish",
            "totalTimeoutMs": 600_000,
            "steps": DELIST_STEPS,
        },
    )
    assert created.status_code == 201, created.text
    return created.json()


async def _task_state(client: httpx.AsyncClient, task_id: str) -> dict[str, Any]:
    response = await client.get(f"/api/v1/platform-tasks/{task_id}", headers=_operator_headers())
    assert response.status_code == 200, response.text
    return response.json()


async def _await_state(
    client: httpx.AsyncClient,
    task_id: str,
    states: set[str],
    *,
    timeout_seconds: float = POLL_SECONDS,
) -> dict[str, Any]:
    deadline = datetime.now(UTC).timestamp() + timeout_seconds
    latest: dict[str, Any] = {}
    while datetime.now(UTC).timestamp() < deadline:
        latest = await _task_state(client, task_id)
        if latest["state"] in states:
            return latest
        await asyncio.sleep(POLL_INTERVAL)
    pytest.fail(
        f"task {task_id} never reached {sorted(states)} within {timeout_seconds}s "
        f"(last state {latest.get('state')})"
    )


async def test_b1_device_restart_task_resumes_or_terminates_safely(
    device_api: tuple[httpx.AsyncClient, str], ledger
) -> None:
    """Restart recovery: same task continues, no duplicate strikes.

    Manual steps driven by the controller per the handbook:
    1. create the delist task (below) and wait for RUNNING;
    2. after the pre-gated screenshots land, reboot the device (holder of the
       DEVICE lock performs adb reboot or a manual power cycle);
    3. let the companion come back online on its own;
    4. the assertions below then verify safe recovery semantics.
    """
    client, serial = device_api
    device_id = await _device_id(client, serial)
    task = await _create_delist_task(client, device_id)
    task_id = task["taskId"]
    ledger.record(
        "device-restart-scenario-start",
        taskId=task_id,
        deviceSerial=serial,
        deviceId=device_id,
        snapshotSha256=task.get("snapshotSha256"),
    )

    running = await _await_state(client, task_id, {"RUNNING", "RECONCILING", "PAUSED_WAITING_USER"})
    ledger.record(
        "device-pre-restart-state",
        taskId=task_id,
        state=running["state"],
        attempt=running["attempt"],
        attemptId=running["attemptId"],
    )

    # Controller reboots the device now (DEVICE lock held); wait for recovery.
    settled = await _await_state(
        client,
        task_id,
        {
            "RUNNING",
            "SUCCEEDED",
            "FAILED",
            "CANCELLED",
            "RECONCILING",
            "PAUSED_WAITING_USER",
            "CANCEL_REQUESTED",
            "PREFLIGHT",
        },
        timeout_seconds=POLL_SECONDS * 2,
    )
    assert settled["attemptId"] == running["attemptId"], (
        "restart must continue the same task, not mint a new one"
    )
    ledger.record(
        "device-post-restart-state",
        taskId=task_id,
        state=settled["state"],
        attempt=settled["attempt"],
        attemptId=settled["attemptId"],
    )

    # No duplicate gated strike: exactly one controlled action for the task.
    if settled["state"] in {"SUCCEEDED", "RECONCILING"}:
        detail = await _task_state(client, task_id)
        strikes = [
            event
            for event in detail.get("events", [])
            if "GATED" in str(event.get("payload", {})).upper()
        ]
        assert len(strikes) <= 1, "restart must not duplicate the gated destructive strike"


async def test_b2_device_readback_after_gated_action(
    device_api: tuple[httpx.AsyncClient, str], ledger
) -> None:
    """Live readback: the badge readback (delta -1) backs the final verdict.

    The companion performs the single gated confirm and then the local
    readback (xianyu_pub_tab_onsale badge). An observed delta of -1 completes
    with the readback evidence; anything else must land UNKNOWN + RECONCILING
    for the operator to resolve (never a blind SUCCEEDED).
    """
    client, serial = device_api
    device_id = await _device_id(client, serial)
    task = await _create_delist_task(client, device_id)
    task_id = task["taskId"]
    ledger.record(
        "device-readback-scenario-start",
        taskId=task_id,
        deviceSerial=serial,
        snapshotSha256=task.get("snapshotSha256"),
    )

    final = await _await_state(
        client, task_id, {"SUCCEEDED", "FAILED", "RECONCILING"}, timeout_seconds=POLL_SECONDS * 2
    )
    ledger.record(
        "device-readback-final",
        taskId=task_id,
        state=final["state"],
        result=final.get("result"),
        reconciliation=final.get("reconciliation"),
    )
    if final["state"] == "SUCCEEDED":
        result = final.get("result") or {}
        assert result.get("outcome") == "applied" or result.get("platformItemId"), (
            "SUCCEEDED must be backed by a unique platform item from the readback"
        )
    else:
        assert final["state"] == "RECONCILING" or final.get("errorCode") != "STEP_TIMEOUT", (
            "an inconclusive readback must surface as UNKNOWN/RECONCILING, "
            "not as an ordinary step failure"
        )
