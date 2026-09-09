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
    assert first.status_code == 200, first.text
    assert first.json()["count"] == 2
    task_ids = {item["taskId"] for item in first.json()["items"]}
    assert len(task_ids) == 2
    replay = await client.post(
        f"/api/v1/task-schedules/{schedule_id}:fire",
        headers=identity(),
        json={"scheduledFor": fire_at.isoformat()},
    )
    assert replay.status_code == 200
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
    assert fired.status_code == 200, fired.text
    assert fired.json()["count"] == 10
    assert len({item["taskId"] for item in fired.json()["items"]}) == 10
