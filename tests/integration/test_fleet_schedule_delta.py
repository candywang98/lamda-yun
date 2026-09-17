"""F12 fleet scheduling delta tests: due-mint idempotency, DST goldens,
template pinning, cancel semantics, A04 key compatibility.

Covers the five acceptance groups of task card F12
(fleet-first-20260916.1「立即/定时/周期调度与取消语义」) against the real
control-api app (memory repository) plus the temporal-worker contracts:

1. repeated tick / worker crash recovery → no double mint (same fire key
   replays the same MobileTask; 201 first / 200 replay);
2. DST jump, repeated hour, UTC↔local conversion → golden pins;
3. template edits never drift minted tasks; future fires use the new revision;
4. cancelling a schedule stops future triggers only; minted tasks stay for
   individual platform-tasks :cancel; no device/account migration;
5. fire key format stays byte-compatible with the A04/K03 manual fire path.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from cloudctl_api import create_app
from cloudctl_api.features.schedules import (
    MISS_POLICY_COALESCE_LATEST,
    classify_due_occurrences,
    occurrence_grid,
    period_marker,
    resolve_miss_policy,
)
from cloudctl_api.features.schedules import (
    fire_key as fleet_fire_key,
)
from cloudctl_api.settings import Settings
from cloudctl_worker.fleet_schedule import (
    FleetScheduleMintInput,
    InMemoryScheduleBackend,
    mint_workflow_id,
)
from fastapi import FastAPI

TENANT = "00000000-0000-7000-8000-000000000111"
OPERATOR = "00000000-0000-7000-8000-000000000222"


def parse_instant(value: str) -> datetime:
    moment = datetime.fromisoformat(value)
    return moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment.astimezone(UTC)


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


async def setup_bound(client: httpx.AsyncClient, count: int = 1) -> tuple[str, list[str]]:
    devices: list[str] = []
    for index in range(count):
        created = await client.post(
            "/api/v1/mobile/devices",
            headers=identity(),
            json={
                "logicalName": f"f12-phone-{uuid.uuid4().hex[:6]}-{index}",
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
            "externalSubjectRef": f"f12-account-{uuid.uuid4().hex[:6]}",
            "displayLabel": "f12",
            "secretRef": "vault://cloudctl/accounts/f12",
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


async def create_recurring(
    client: httpx.AsyncClient,
    account_id: str,
    device_ids: list[str],
    *,
    miss_policy: str = "QUEUE_ONE",
    command_type: str = "device.probe_capabilities.v1",
    parameters: dict | None = None,
) -> tuple[str, datetime]:
    created = await client.post(
        "/api/v1/task-schedules",
        headers=identity(),
        json={
            "timezone": "Asia/Shanghai",
            "kind": "RECURRING",
            "rrule": "FREQ=DAILY;INTERVAL=1",
            "missPolicy": miss_policy,
            "accountId": account_id,
            "deviceIds": device_ids,
            "commandType": command_type,
            "parameters": parameters or {},
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    created_at = datetime.fromisoformat(body["createdAt"])
    return str(body["id"]), created_at


def floored(value: datetime) -> datetime:
    """Grid anchors drop seconds/microseconds (stable fire identity)."""
    return value.replace(second=0, microsecond=0)


async def mint_due(
    client: httpx.AsyncClient, schedule_id: str, now: datetime
) -> httpx.Response:
    return await client.post(
        f"/api/v1/fleet-schedules/{schedule_id}:mint-due",
        headers=identity(),
        json={"now": now.isoformat()},
    )


# ---------------------------------------------------------------------------
# Group 1 — repeated tick / worker crash recovery never double-mints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_repeated_tick_and_crash_recovery_do_not_double_mint(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, _ = api
    account_id, devices = await setup_bound(client, 1)
    schedule_id, created_at = await create_recurring(client, account_id, devices)

    first_due = created_at + timedelta(days=1, minutes=5)
    first = await mint_due(client, schedule_id, first_due)
    assert first.status_code == 201, first.text
    assert first.headers["Idempotency-Replayed"] == "false"
    assert len(first.json()["taskIds"]) == 1
    task_id = first.json()["taskIds"][0]

    # Repeated tick on the same period → replay, never a second mint.
    second = await mint_due(client, schedule_id, first_due + timedelta(minutes=10))
    assert second.status_code == 200, second.text
    assert second.headers["Idempotency-Replayed"] == "true"
    assert second.json()["taskIds"] == [task_id]
    assert second.json()["createdAny"] is False

    # Worker crash recovery re-runs the same mint activity → same key, same task.
    third = await mint_due(client, schedule_id, first_due + timedelta(hours=2))
    assert third.status_code == 200
    assert third.json()["taskIds"] == [task_id]

    listed = await client.get(
        "/api/v1/platform-tasks", headers=identity(), params={"deviceId": devices[0]}
    )
    assert listed.status_code == 200, listed.text
    assert [item["taskId"] for item in listed.json()["items"]] == [task_id]

    # A later period is a different fire identity → a fresh task is minted.
    next_period = await mint_due(client, schedule_id, created_at + timedelta(days=2, minutes=5))
    assert next_period.status_code == 201, next_period.text
    assert next_period.json()["taskIds"] != [task_id]


@pytest.mark.asyncio
async def test_worker_backend_and_workflow_id_are_deterministic() -> None:
    backend = InMemoryScheduleBackend()
    command = FleetScheduleMintInput(
        tenant_id=TENANT,
        schedule_id="sched-1",
        period_marker="2026-09-17T12:00:00+00:00",
        scheduled_for="2026-09-17T12:00:00+00:00",
    )
    first = await backend.mint_due(command)
    assert first.created_any is True
    replay = await backend.mint_due(command)
    assert replay.created_any is False
    assert replay.task_ids == first.task_ids
    assert backend.mint_calls[("sched-1", command.period_marker)] == 2

    # Tick-level fire identity: same (schedule, period) → same workflow id.
    assert mint_workflow_id("sched-1", "2026-09-17T12:00:00+00:00") == mint_workflow_id(
        "sched-1", "2026-09-17T12:00:00+00:00"
    )
    assert mint_workflow_id("sched-1", "2026-09-17T12:00:00+00:00") != mint_workflow_id(
        "sched-1", "2026-09-18T12:00:00+00:00"
    )

    polled = await backend.poll_due(TENANT)
    assert polled == ()  # nothing queued


async def test_poll_due_lists_only_unminted_periods(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, _ = api
    account_id, devices = await setup_bound(client, 1)
    schedule_id, created_at = await create_recurring(client, account_id, devices)
    now = created_at + timedelta(days=1, minutes=5)

    poll = await client.post(
        "/api/v1/fleet-schedules:poll", headers=identity(), json={"now": now.isoformat()}
    )
    assert poll.status_code == 200
    due_ids = [item["scheduleId"] for item in poll.json()["items"]]
    assert schedule_id in due_ids
    marker = next(
        item["periodMarker"] for item in poll.json()["items"] if item["scheduleId"] == schedule_id
    )
    assert marker.endswith("+00:00")

    minted = await mint_due(client, schedule_id, now)
    assert minted.status_code == 201, minted.text

    again = await client.post(
        "/api/v1/fleet-schedules:poll",
        headers=identity(),
        json={"now": (now + timedelta(minutes=30)).isoformat()},
    )
    assert again.status_code == 200
    assert schedule_id not in [item["scheduleId"] for item in again.json()["items"]]


# ---------------------------------------------------------------------------
# Group 2 — DST jump / repeated hour / UTC↔local goldens
# ---------------------------------------------------------------------------


def test_dst_spring_forward_shifts_missing_local_hour() -> None:
    # DAILY 02:30 America/New_York: 2026-03-08 has no local 02:30 (gap).
    # 2026-03-07 02:30 EST == 07:30 UTC is the anchor instant.
    anchor = datetime(2026, 3, 7, 7, 30, tzinfo=UTC)
    grid = occurrence_grid(
        "America/New_York",
        "FREQ=DAILY;INTERVAL=1",
        anchor=anchor,
        through=datetime(2026, 3, 9, 0, 0, tzinfo=UTC),
    )
    by_label = {item.local_label: item for item in grid}
    assert "2026-03-08T02:30:00-05:00" not in by_label  # nonexistent wall time
    shifted = by_label["2026-03-08T03:30:00-04:00"]  # gap shifts forward
    assert period_marker(shifted.utc) == "2026-03-08T07:30:00+00:00"


def test_dst_fall_back_daily_takes_first_fold() -> None:
    # DAILY 01:30 America/New_York on 2026-11-01 is ambiguous; fold=0 wins.
    # 2026-10-31 01:30 EDT == 05:30 UTC is the anchor instant.
    anchor = datetime(2026, 10, 31, 5, 30, tzinfo=UTC)
    grid = occurrence_grid(
        "America/New_York",
        "FREQ=DAILY;INTERVAL=1",
        anchor=anchor,
        through=datetime(2026, 11, 2, 0, 0, tzinfo=UTC),
    )
    labels = [item.local_label for item in grid]
    assert "2026-11-01T01:30:00-04:00" in labels  # fold=0 (EDT, first pass)
    assert "2026-11-01T01:30:00-05:00" not in labels  # DAILY never takes fold=1
    first = next(item for item in grid if item.local_label.endswith("11-01T01:30:00-04:00"))
    assert period_marker(first.utc) == "2026-11-01T05:30:00+00:00"


def test_hourly_repeated_hour_mints_two_distinct_periods() -> None:
    # HOURLY steps in absolute time: the repeated local hour is two periods.
    anchor = datetime(2026, 11, 1, 4, 30, tzinfo=UTC)  # 00:30 EDT
    grid = occurrence_grid(
        "America/New_York",
        "FREQ=HOURLY;INTERVAL=1",
        anchor=anchor,
        through=datetime(2026, 11, 1, 8, 0, tzinfo=UTC),
    )
    markers = [item.marker for item in grid]
    assert "2026-11-01T05:30:00+00:00" in markers  # 01:30 EDT (fold=0)
    assert "2026-11-01T06:30:00+00:00" in markers  # 01:30 EST (fold=1)
    repeated = [item for item in grid if "01:30" in item.local_label]
    assert len(repeated) == 2
    assert {item.local_label for item in repeated} == {
        "2026-11-01T01:30:00-04:00",
        "2026-11-01T01:30:00-05:00#fold",
    }


def test_utc_local_roundtrip_marker_is_stable() -> None:
    # Markers depend only on the persisted anchor, never on query wall time.
    anchor = datetime(2026, 6, 1, 9, 0, tzinfo=UTC)
    early = occurrence_grid(
        "Asia/Shanghai", "FREQ=DAILY;INTERVAL=1", anchor=anchor, through=anchor + timedelta(days=2)
    )
    late = occurrence_grid(
        "Asia/Shanghai", "FREQ=DAILY;INTERVAL=1", anchor=anchor, through=anchor + timedelta(days=5)
    )
    assert late[: len(early)] == early
    assert early[0].local_label == "2026-06-02T17:00:00+08:00"
    assert early[0].marker == "2026-06-02T09:00:00+00:00"


# ---------------------------------------------------------------------------
# Group 3 — template edits never drift minted tasks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_template_edit_pins_minted_task_and_future_uses_new_revision(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = api
    account_id, devices = await setup_bound(client, 1)
    schedule_id, created_at = await create_recurring(
        client,
        account_id,
        devices,
        command_type="xianyu.collect_orders.v1",
        parameters={"role": "ALL_VISIBLE", "limit": 3},
    )

    first = await mint_due(client, schedule_id, created_at + timedelta(days=1, minutes=5))
    assert first.status_code == 201, first.text
    first_task_id = first.json()["taskIds"][0]

    # Simulate a template edit after the mint (no public edit endpoint yet).
    from cloudctl_api.db import TaskScheduleRow

    async with app.state.database.unit_of_work() as session:
        row = await session.get(TaskScheduleRow, schedule_id)
        assert row is not None
        row.parameters = {"role": "SOLD", "limit": 10}
        row.template_revision = 2

    second = await mint_due(client, schedule_id, created_at + timedelta(days=2, minutes=5))
    assert second.status_code == 201, second.text
    second_mint = next(
        decision for decision in second.json()["decisions"] if decision["action"] == "MINT"
    )
    second_task_id = second_mint["items"][0]["taskId"]
    assert second_task_id != first_task_id

    frozen = await client.get(f"/api/v1/platform-tasks/{first_task_id}", headers=identity())
    assert frozen.status_code == 200, frozen.text
    payload = frozen.json()["commandPayload"]
    assert payload["parameters"] == {"role": "ALL_VISIBLE", "limit": 3}
    assert payload["templateRevision"] == 1
    assert parse_instant(frozen.json()["scheduledFor"]) == floored(created_at) + timedelta(
        days=1
    )
    assert payload["snapshotSha256"]

    fresh = await client.get(f"/api/v1/platform-tasks/{second_task_id}", headers=identity())
    assert fresh.status_code == 200, fresh.text
    assert fresh.json()["commandPayload"]["parameters"] == {"role": "SOLD", "limit": 10}
    assert fresh.json()["commandPayload"]["templateRevision"] == 2


# ---------------------------------------------------------------------------
# Group 4 — cancel stops the future only; minted tasks stay; no migration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_stops_future_mints_and_keeps_minted_tasks(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, _ = api
    account_id, devices = await setup_bound(client, 1)
    schedule_id, created_at = await create_recurring(client, account_id, devices)

    minted = await mint_due(client, schedule_id, created_at + timedelta(days=1, minutes=5))
    assert minted.status_code == 201, minted.text
    task_id = minted.json()["taskIds"][0]

    cancelled = await client.post(
        f"/api/v1/fleet-schedules/{schedule_id}:cancel",
        headers=identity(),
        json={"reason": "campaign ended"},
    )
    assert cancelled.status_code == 200, cancelled.text
    body = cancelled.json()
    assert body["status"] == "CANCELLED"
    assert body["mintedTaskIds"] == [task_id]  # listed, NOT auto-cancelled

    # Future periods refuse to mint — a 409, never a silent fire.
    future = await mint_due(client, schedule_id, created_at + timedelta(days=3, minutes=5))
    assert future.status_code == 409, future.text
    assert "cancelled" in future.json()["detail"].lower()

    poll = await client.post(
        "/api/v1/fleet-schedules:poll",
        headers=identity(),
        json={"now": (created_at + timedelta(days=3, minutes=5)).isoformat()},
    )
    assert poll.status_code == 200
    assert schedule_id not in [item["scheduleId"] for item in poll.json()["items"]]

    # The minted task survives untouched, waiting for an individual cancel.
    task = await client.get(f"/api/v1/platform-tasks/{task_id}", headers=identity())
    assert task.status_code == 200
    assert task.json()["state"] == "QUEUED"

    per_task = await client.post(
        f"/api/v1/platform-tasks/{task_id}:cancel",
        headers=identity(),
        json={"reason": "operator cancelled the leftover schedule task"},
    )
    assert per_task.status_code == 200, per_task.text
    assert per_task.json()["state"] == "CANCELLED"

    # Cancel replay is idempotent.
    replay = await client.post(
        f"/api/v1/fleet-schedules/{schedule_id}:cancel",
        headers=identity(),
        json={"reason": "campaign ended"},
    )
    assert replay.status_code == 200
    assert replay.json()["mintedTaskIds"] == [task_id]


@pytest.mark.asyncio
async def test_broken_binding_errors_on_device_and_never_migrates(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, _ = api
    account_id, devices = await setup_bound(client, 2)
    healthy, orphan = devices
    schedule_id, created_at = await create_recurring(client, account_id, devices)

    # The orphan device loses its binding before the fire (device offline /
    # account unbound): the mint must fail ON that device, not migrate.
    unbound = await client.delete(
        f"/api/v1/accounts/{account_id}/bindings/{orphan}", headers=identity()
    )
    assert unbound.status_code == 204, unbound.text

    minted = await mint_due(client, schedule_id, created_at + timedelta(days=1, minutes=5))
    assert minted.status_code == 201, minted.text
    items = minted.json()["decisions"][0]["items"]
    by_device = {item["deviceId"]: item for item in items}
    assert by_device[healthy]["status"] == "QUEUED"
    assert by_device[orphan]["status"] == "ERROR"
    assert by_device[orphan]["taskId"] is None

    # Exactly one task exists — on the original healthy device, original account.
    task_id = minted.json()["taskIds"][0]
    task = await client.get(f"/api/v1/platform-tasks/{task_id}", headers=identity())
    assert task.status_code == 200
    assert task.json()["deviceId"] == healthy
    assert task.json()["accountId"] == account_id


# ---------------------------------------------------------------------------
# Group 5 — fire key format / A04 create idempotency compatibility
# ---------------------------------------------------------------------------


def test_fire_key_formula_is_a04_compatible() -> None:
    schedule_id = "6f0f9dd4-2a9b-4e1f-9f6d-000000000001"
    device_id = "6f0f9dd4-2a9b-4e1f-9f6d-000000000002"
    occurrence = datetime(2026, 9, 18, 1, 30, tzinfo=UTC)
    expected = hashlib.sha256(
        f"{schedule_id}:{occurrence.isoformat()}:{device_id}".encode()
    ).hexdigest()[:64]
    assert fleet_fire_key(schedule_id, occurrence, device_id) == expected
    assert len(expected) == 64
    # Same period, same key; any other period differs.
    assert fleet_fire_key(
        schedule_id, occurrence + timedelta(days=1), device_id
    ) != fleet_fire_key(schedule_id, occurrence, device_id)


@pytest.mark.asyncio
async def test_fleet_mint_replays_through_legacy_manual_fire_route(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    """Byte-compatibility with the frozen A04/K03 path: after a fleet mint,
    the legacy :fire route with the same scheduledFor must answer 200 replay
    with the identical taskId (shared ledger rows + identical key formula).
    """
    client, _ = api
    account_id, devices = await setup_bound(client, 1)
    schedule_id, created_at = await create_recurring(client, account_id, devices)
    occurrence = floored(created_at) + timedelta(days=1)

    minted = await mint_due(client, schedule_id, created_at + timedelta(days=1, minutes=5))
    assert minted.status_code == 201, minted.text
    task_id = minted.json()["taskIds"][0]
    marker = minted.json()["decisions"][0]["periodMarker"]
    assert marker == period_marker(occurrence)

    legacy = await client.post(
        f"/api/v1/task-schedules/{schedule_id}:fire",
        headers=identity(),
        json={"scheduledFor": occurrence.isoformat()},
    )
    assert legacy.status_code == 200, legacy.text
    assert legacy.headers["Idempotency-Replayed"] == "true"
    assert legacy.json()["taskIds"] == [task_id]


# ---------------------------------------------------------------------------
# Missed-fire policy (explicit redesign, window-free)
# ---------------------------------------------------------------------------


def test_miss_policy_resolution_and_classification() -> None:
    assert resolve_miss_policy("QUEUE_ONE") == MISS_POLICY_COALESCE_LATEST
    assert resolve_miss_policy("COALESCE_LATEST") == MISS_POLICY_COALESCE_LATEST
    assert resolve_miss_policy("SKIP") == "SKIP"

    def occ(day: int) -> object:
        return type(
            "Occ",
            (),
            {"utc": datetime(2026, 9, day, 6, 0, tzinfo=UTC), "marker": f"2026-09-{day:02d}"},
        )()

    # Single due occurrence = current period: minted under both policies.
    both = classify_due_occurrences([occ(17)], "QUEUE_ONE")
    assert both.mint is not None and not both.skipped
    skip_policy_single = classify_due_occurrences([occ(17)], "SKIP")
    assert skip_policy_single.mint is not None
    # Backlog: COALESCE_LATEST mints only the newest; SKIP drops the backlog.
    backlog = [occ(15), occ(16), occ(17)]
    coalesced = classify_due_occurrences(backlog, "QUEUE_ONE")
    assert coalesced.mint is not None and coalesced.mint.marker == "2026-09-17"
    assert [skip.occurrence.marker for skip in coalesced.skipped] == ["2026-09-15", "2026-09-16"]
    dropped = classify_due_occurrences(backlog, "SKIP")
    assert dropped.mint is None
    assert len(dropped.skipped) == 3


@pytest.mark.asyncio
async def test_coalesce_latest_backfills_exactly_one_after_downtime(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, _ = api
    account_id, devices = await setup_bound(client, 1)
    schedule_id, created_at = await create_recurring(client, account_id, devices)

    # Worker down for 3+ days: 3 due unminted DAILY periods → one mint.
    recovered = await mint_due(client, schedule_id, created_at + timedelta(days=3, minutes=5))
    assert recovered.status_code == 201, recovered.text
    decisions = recovered.json()["decisions"]
    minted = [item for item in decisions if item["action"] == "MINT"]
    skipped = [item for item in decisions if item["action"] == "SKIP"]
    assert len(minted) == 1
    assert len(skipped) == 2
    assert parse_instant(minted[0]["scheduledFor"]) == floored(created_at) + timedelta(days=3)
    assert len(recovered.json()["taskIds"]) == 1
    assert "coalesced" in skipped[0]["detail"]

    # Re-running the catch-up tick changes nothing: same task, replayed.
    replay = await mint_due(client, schedule_id, created_at + timedelta(days=3, hours=6))
    assert replay.status_code == 200
    assert replay.json()["taskIds"] == recovered.json()["taskIds"]
    replay_decisions = replay.json()["decisions"]
    assert [d["action"] for d in replay_decisions] == ["REPLAY"]
    assert replay_decisions[0]["items"][0]["status"] == "QUEUED"


@pytest.mark.asyncio
async def test_skip_policy_drops_backlog_and_resumes_next_period(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, _ = api
    account_id, devices = await setup_bound(client, 1)
    schedule_id, created_at = await create_recurring(
        client, account_id, devices, miss_policy="SKIP"
    )

    backlog = await mint_due(client, schedule_id, created_at + timedelta(days=3, minutes=5))
    assert backlog.status_code == 200, backlog.text  # nothing minted
    assert backlog.json()["taskIds"] == []
    assert len([d for d in backlog.json()["decisions"] if d["action"] == "SKIP"]) == 3

    # The next fresh period mints normally.
    fresh = await mint_due(client, schedule_id, created_at + timedelta(days=4, minutes=5))
    assert fresh.status_code == 201, fresh.text
    assert len(fresh.json()["taskIds"]) == 1


@pytest.mark.asyncio
async def test_once_schedule_late_recovery_mints_with_original_scheduled_for(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, _ = api
    account_id, devices = await setup_bound(client, 1)
    once_at = datetime.now(UTC) - timedelta(days=2)
    created = await client.post(
        "/api/v1/task-schedules",
        headers=identity(),
        json={
            "timezone": "Asia/Shanghai",
            "kind": "ONCE",
            "onceAt": once_at.isoformat(),
            "missPolicy": "QUEUE_ONE",
            "accountId": account_id,
            "deviceIds": devices,
            "commandType": "device.probe_capabilities.v1",
            "parameters": {},
        },
    )
    # Old create refuses past onceAt — seed the row directly for the recovery
    # scenario (a schedule whose fire time passed while the worker was down).
    assert created.status_code == 422
    from cloudctl_api.db import TaskScheduleRow

    app = client._transport.app  # noqa: SLF001 - test hook into the ASGI app
    schedule_id = str(uuid.uuid4())
    async with app.state.database.unit_of_work() as session:
        session.add(
            TaskScheduleRow(
                id=schedule_id,
                tenant_id=TENANT,
                timezone="Asia/Shanghai",
                kind="ONCE",
                once_at=once_at,
                rrule=None,
                enabled=True,
                template_revision=1,
                miss_policy="QUEUE_ONE",
                start_deadline_minutes=30,
                account_id=account_id,
                binding_version=1,
                device_ids=devices,
                command_type="device.probe_capabilities.v1",
                parameters={},
                created_by=OPERATOR,
                paused_reason=None,
                last_error=None,
                created_at=once_at - timedelta(minutes=10),
            )
        )

    late = await mint_due(client, schedule_id, datetime.now(UTC))
    assert late.status_code == 201, late.text
    assert len(late.json()["taskIds"]) == 1
    task_id = late.json()["taskIds"][0]
    task = await client.get(f"/api/v1/platform-tasks/{task_id}", headers=identity())
    assert task.status_code == 200
    # The original fire instant is stamped, not the recovery moment.
    assert parse_instant(task.json()["scheduledFor"]) == once_at
