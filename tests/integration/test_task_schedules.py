from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from cloudctl_api import create_app
from cloudctl_api.schedules import next_occurrences
from cloudctl_api.settings import Settings
from fastapi import FastAPI

TENANT = "00000000-0000-7000-8000-000000000111"
OPERATOR = "00000000-0000-7000-8000-000000000222"


def identity() -> dict[str, str]:
    return {
        "X-Tenant-Id": TENANT,
        "X-User-Id": OPERATOR,
        "X-Roles": "device_operator",
        "X-MFA": "true",
        "X-Request-Id": str(uuid.uuid4()),
    }


@pytest.fixture
async def api() -> AsyncIterator[tuple[httpx.AsyncClient, FastAPI]]:
    app = create_app(Settings(env="test", repository_mode="memory", dev_auth_bypass=True))
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, app


async def setup_bound(client: httpx.AsyncClient, count: int = 2) -> tuple[str, list[str]]:
    devices: list[str] = []
    for index in range(count):
        created = await client.post(
            "/api/v1/mobile/devices",
            headers=identity(),
            json={
                "logicalName": f"sched-phone-{index}",
                "androidVersion": "14",
                "companionVersion": "1.0.0",
            },
        )
        assert created.status_code == 201, created.text
        devices.append(str(created.json()["id"]))
    account = await client.post(
        "/api/v1/accounts",
        headers=identity(),
        json={
            "platform": "xianyu",
            "externalSubjectRef": "sched-account",
            "displayLabel": "sched",
            "secretRef": "vault://cloudctl/accounts/sched",
            "authorizationBasis": "Owner authorized.",
        },
    )
    assert account.status_code == 201, account.text
    account_id = str(account.json()["id"])
    for device_id in devices:
        bound = await client.post(
            f"/api/v1/accounts/{account_id}/bindings",
            headers=identity(),
            json={"deviceId": device_id, "confirmationNote": "Owner confirmed."},
        )
        assert bound.status_code == 201, bound.text
    return account_id, devices


def test_dst_spring_forward_skips_missing_hour() -> None:
    from zoneinfo import ZoneInfo

    zone = ZoneInfo("America/New_York")
    before = datetime(2026, 3, 7, 12, 0, tzinfo=zone)
    values = next_occurrences("America/New_York", "FREQ=DAILY", after=before, count=2)
    assert values[0].tzinfo is UTC
    local_hours = [item.astimezone(zone).hour for item in values]
    assert local_hours[0] == local_hours[1]


@pytest.mark.asyncio
async def test_schedule_fire_is_idempotent_and_disabled_stops(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, _ = api
    account_id, devices = await setup_bound(client, 2)
    once_at = datetime.now(UTC) + timedelta(hours=2)
    created = await client.post(
        "/api/v1/task-schedules",
        headers=identity(),
        json={
            "timezone": "Asia/Shanghai",
            "kind": "ONCE",
            "onceAt": once_at.isoformat(),
            "accountId": account_id,
            "deviceIds": devices,
            "commandType": "device.probe_capabilities.v1",
            "parameters": {},
        },
    )
    assert created.status_code == 201, created.text
    schedule_id = created.json()["id"]
    assert created.json()["bindingVersion"] >= 1
    fire_at = datetime.now(UTC)
    first = await client.post(
        f"/api/v1/task-schedules/{schedule_id}:fire",
        headers=identity(),
        json={"scheduledFor": fire_at.isoformat()},
    )
    # task-schedule/v1 §5: first fire mints (201); replay is idempotent (200).
    assert first.status_code == 201, first.text
    assert first.json()["count"] == 2
    assert first.headers["Idempotency-Replayed"] == "false"
    task_ids = {item["taskId"] for item in first.json()["items"]}
    assert len(task_ids) == 2
    assert len(first.json()["taskIds"]) == 2
    replay = await client.post(
        f"/api/v1/task-schedules/{schedule_id}:fire",
        headers=identity(),
        json={"scheduledFor": fire_at.isoformat()},
    )
    assert replay.status_code == 200
    assert replay.headers["Idempotency-Replayed"] == "true"
    assert {item["taskId"] for item in replay.json()["items"]} == task_ids
    disabled = await client.post(
        f"/api/v1/task-schedules/{schedule_id}:disable",
        headers=identity(),
    )
    assert disabled.status_code == 200
    assert disabled.json()["enabled"] is False
    later = await client.post(
        f"/api/v1/task-schedules/{schedule_id}:fire",
        headers=identity(),
        json={"scheduledFor": (fire_at + timedelta(days=1)).isoformat()},
    )
    assert later.status_code == 409


@pytest.mark.asyncio
async def test_ten_devices_mint_ten_tasks(api: tuple[httpx.AsyncClient, FastAPI]) -> None:
    client, _ = api
    account_id, devices = await setup_bound(client, 10)
    created = await client.post(
        "/api/v1/task-schedules",
        headers=identity(),
        json={
            "timezone": "Asia/Shanghai",
            "kind": "RECURRING",
            "rrule": "FREQ=DAILY;INTERVAL=1",
            "accountId": account_id,
            "deviceIds": devices,
            "commandType": "device.probe_capabilities.v1",
            "parameters": {},
        },
    )
    assert created.status_code == 201, created.text
    assert len(created.json()["nextOccurrences"]) == 3
    fired = await client.post(
        f"/api/v1/task-schedules/{created.json()['id']}:fire",
        headers=identity(),
        json={"scheduledFor": datetime.now(UTC).isoformat()},
    )
    assert fired.status_code == 201, fired.text
    assert fired.json()["count"] == 10
    assert len({item["taskId"] for item in fired.json()["items"]}) == 10


@pytest.mark.asyncio
async def test_k03_once_schedule_fire_is_idempotent(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    """K03 fixture k03-positive-schedule-once: same fire key twice mints one task.

    Contract task-schedule/v1@20260916.1 §5-§6: fire key =
    sha256(schedule_id:utc_time:device_id)[:64], TaskScheduleFireRow
    Unique(schedule_id, scheduled_for, device_id) backstop, first fire 201 /
    replay 200 distinguishable. Fixture commandType xianyu.polish.steps.v1 is
    not in the frozen CommandV1 CommandType set (contract §1 scope), so the
    closest frozen type device.probe_capabilities.v1 stands in.
    """
    client, _ = api
    account_id, devices = await setup_bound(client, 1)
    device_id = devices[0]
    once_at = datetime.now(UTC) + timedelta(hours=2)
    created = await client.post(
        "/api/v1/task-schedules",
        headers=identity(),
        json={
            "timezone": "Asia/Shanghai",
            "kind": "ONCE",
            "onceAt": once_at.isoformat(),
            "missPolicy": "QUEUE_ONE",
            "startDeadlineMinutes": 30,
            "accountId": account_id,
            "deviceIds": [device_id],
            "commandType": "device.probe_capabilities.v1",
            "parameters": {},
        },
    )
    assert created.status_code == 201, created.text
    schedule_id = created.json()["id"]

    fire_body = {"scheduledFor": once_at.isoformat(), "deviceId": device_id}
    first = await client.post(
        f"/api/v1/task-schedules/{schedule_id}:fire",
        headers=identity(),
        json=fire_body,
    )
    assert first.status_code == 201, first.text
    assert first.headers["Idempotency-Replayed"] == "false"
    assert len(first.json()["taskIds"]) == 1
    task_id = first.json()["taskIds"][0]

    replay = await client.post(
        f"/api/v1/task-schedules/{schedule_id}:fire",
        headers=identity(),
        json=fire_body,
    )
    assert replay.status_code == 200, replay.text
    assert replay.headers["Idempotency-Replayed"] == "true"
    assert replay.json()["taskIds"] == [task_id]

    listed = await client.get(
        "/api/v1/platform-tasks", headers=identity(), params={"deviceId": device_id, "limit": 50}
    )
    assert listed.status_code == 200, listed.text
    assert [item["taskId"] for item in listed.json()["items"]] == [task_id]

    detail = await client.get(f"/api/v1/task-schedules/{schedule_id}", headers=identity())
    assert detail.status_code == 200, detail.text
    fires = detail.json()["fires"]
    assert len(fires) == 1
    assert fires[0]["taskId"] == task_id
    assert fires[0]["status"] == "QUEUED"

    task = await client.get(f"/api/v1/platform-tasks/{task_id}", headers=identity())
    assert task.status_code == 200, task.text
    assert task.json()["commandPayload"]["templateRevision"] == 1


@pytest.mark.asyncio
async def test_k03_rrule_monthly_rejected(api: tuple[httpx.AsyncClient, FastAPI]) -> None:
    """K03 fixture k03-negative-rrule-monthly: restricted rrule subset (D3)."""
    client, _ = api
    account_id, devices = await setup_bound(client, 1)
    rejected = await client.post(
        "/api/v1/task-schedules",
        headers=identity(),
        json={
            "kind": "RECURRING",
            "rrule": "FREQ=MONTHLY;INTERVAL=1",
            "timezone": "Asia/Shanghai",
            "accountId": account_id,
            "deviceIds": devices,
            "commandType": "device.probe_capabilities.v1",
            "parameters": {},
        },
    )
    assert rejected.status_code == 422, rejected.text
    problem = rejected.json()
    assert problem["code"] == "VALIDATION_ERROR"
    assert "rrule" in problem["fields"]
    assert "HOURLY" in problem["fields"]["rrule"] or "DAILY" in problem["fields"]["rrule"]


@pytest.mark.asyncio
async def test_k03_fired_task_parameters_frozen_against_template_edits(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    """task-schedule/v1 §5: fire stamps template_revision; editing the template
    afterwards must not drift an already-fired task's frozen parameters."""
    client, app = api
    account_id, devices = await setup_bound(client, 1)
    device_id = devices[0]
    created = await client.post(
        "/api/v1/task-schedules",
        headers=identity(),
        json={
            "timezone": "Asia/Shanghai",
            "kind": "RECURRING",
            "rrule": "FREQ=DAILY;INTERVAL=1",
            "accountId": account_id,
            "deviceIds": [device_id],
            "commandType": "xianyu.collect_orders.v1",
            "parameters": {"role": "ALL_VISIBLE", "limit": 3},
        },
    )
    assert created.status_code == 201, created.text
    schedule_id = created.json()["id"]

    first_fire_at = datetime.now(UTC) - timedelta(minutes=1)
    first = await client.post(
        f"/api/v1/task-schedules/{schedule_id}:fire",
        headers=identity(),
        json={"scheduledFor": first_fire_at.isoformat(), "deviceId": device_id},
    )
    assert first.status_code == 201, first.text
    first_task_id = first.json()["taskIds"][0]

    # Simulate a template edit after the fire (no public edit endpoint yet).
    from cloudctl_api.db import TaskScheduleRow

    async with app.state.database.unit_of_work() as session:
        row = await session.get(TaskScheduleRow, schedule_id)
        assert row is not None
        row.parameters = {"role": "SOLD", "limit": 10}
        row.template_revision = 2

    second_fire_at = datetime.now(UTC) + timedelta(minutes=1)
    second = await client.post(
        f"/api/v1/task-schedules/{schedule_id}:fire",
        headers=identity(),
        json={"scheduledFor": second_fire_at.isoformat(), "deviceId": device_id},
    )
    assert second.status_code == 201, second.text
    second_task_id = second.json()["taskIds"][0]
    assert second_task_id != first_task_id

    frozen = await client.get(f"/api/v1/platform-tasks/{first_task_id}", headers=identity())
    assert frozen.status_code == 200, frozen.text
    assert frozen.json()["commandPayload"]["parameters"] == {"role": "ALL_VISIBLE", "limit": 3}
    assert frozen.json()["commandPayload"]["templateRevision"] == 1
    assert frozen.json()["commandPayload"]["snapshotSha256"]

    fresh = await client.get(f"/api/v1/platform-tasks/{second_task_id}", headers=identity())
    assert fresh.status_code == 200, fresh.text
    assert fresh.json()["commandPayload"]["parameters"] == {"role": "SOLD", "limit": 10}
    assert fresh.json()["commandPayload"]["templateRevision"] == 2
