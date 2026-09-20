"""P43/P44 listing collection (fleet-first-20260916.1 xy-tasks-24): identity
dedupe-upsert, change-triggered snapshot history, screen replay guard,
tenant scoping, and the read-only invariant.

- POST /companion/v2/fleet/listings/screens — per-screen push: new keys,
  unchanged duplicates, changed rows (price/status) append history only on
  change, offline replay is idempotent.
- GET /api/v1/fleet/listings/history — cursor pagination, tenant scoping
  (foreign tenant sees empty), latest snapshot + snapshotCount.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from cloudctl_api import create_app
from cloudctl_api.db import MobileTaskRow
from cloudctl_api.fleet_listings import FleetListingRow, FleetListingSnapshotRow
from cloudctl_api.settings import Settings
from fastapi import FastAPI
from sqlalchemy import select
from test_platform_tasks import _enroll, create_direct_device, identity

OTHER_TENANT = {
    "X-Tenant-Id": "00000000-0000-7000-8000-000000000999",
    "X-User-Id": "00000000-0000-7000-8000-000000000998",
    "X-Roles": "device_operator",
    "X-MFA": "true",
    "X-Request-Id": "00000000-0000-7000-8000-000000000997",
}


@pytest.fixture
async def api() -> AsyncIterator[tuple[httpx.AsyncClient, FastAPI]]:
    app = create_app(Settings(env="test", repository_mode="memory", dev_auth_bypass=True))
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, app


def _row(
    key: str,
    *,
    title: str = "闲置键盘",
    price: int | None = 19900,
    status: str | None = "在售",
) -> dict[str, Any]:
    return {
        "item_key": key,
        "title": title,
        "price_cents": price,
        "price_text": "199" if price is not None else None,
        "status_text": status,
    }


def _screen(
    run: str,
    screen: int,
    rows: list[dict[str, Any]],
    *,
    partial: int = 0,
    collected: str | None = "2026-09-20T12:00:00+00:00",
) -> dict[str, Any]:
    return {
        "schema_version": "listing-collect/20260920.1",
        "run_key": run,
        "screen": screen,
        "collected_at": collected,
        "rows": rows,
        "partial_rows": partial,
    }


async def _push(client: httpx.AsyncClient, auth: dict[str, str], body: dict[str, Any]):
    return await client.post("/companion/v2/fleet/listings/screens", headers=auth, json=body)


async def test_push_dedupe_upsert_and_replay(api):
    client, _app = api
    device = await create_direct_device(client, "listings-dev")
    auth = await _enroll(client, device, "listings-instance")

    first = await _push(client, auth, _screen("run-1", 1, [
        _row("闲置键盘|19900"),
        _row("机械鼠标|8900", title="机械鼠标", price=8900, status="在售"),
    ]))
    assert first.status_code == 201, first.text
    assert first.json()["accepted"] == 2
    assert first.json()["updated"] == 0

    # Same identities again in a later screen of the same run: duplicates.
    second = await _push(client, auth, _screen("run-1", 2, [_row("闲置键盘|19900")]))
    assert second.status_code == 201
    assert second.json()["duplicates"] == 1

    # Identity is the composite key (title|price, frozen like order-sync):
    # a re-priced listing IS a new identity; a same-key STATUS change
    # upserts and appends history only for the change.
    reprice = await _push(client, auth, _screen("run-2", 1, [
        _row("闲置键盘|17900", price=17900),
    ]))
    assert reprice.status_code == 201
    assert reprice.json()["accepted"] == 1

    changed = await _push(client, auth, _screen("run-2", 2, [
        _row("闲置键盘|19900", status="已下架"),
    ]))
    assert changed.status_code == 201
    assert changed.json()["updated"] == 1

    # Offline replay of an already-stored screen never double-counts.
    replay = await _push(client, auth, _screen("run-1", 1, [
        _row("闲置键盘|19900"),
        _row("机械鼠标|8900", title="机械鼠标", price=8900, status="在售"),
    ]))
    assert replay.status_code == 200
    assert replay.json()["replayed"] is True
    assert replay.json()["accepted"] == 0

    async with _app.state.database.unit_of_work() as session:
        rows = {
            row.item_key: row
            for row in await session.scalars(
                select(FleetListingRow).where(FleetListingRow.device_id == device)
            )
        }
        assert set(rows) == {"闲置键盘|19900", "机械鼠标|8900", "闲置键盘|17900"}
        keyboard = rows["闲置键盘|19900"]
        assert keyboard.price_cents == 19900
        assert keyboard.status_text == "已下架"
        assert keyboard.snapshot_count == 2
        assert keyboard.dedupe_marker == "MISSING_ID"
        history = list(
            await session.scalars(
                select(FleetListingSnapshotRow).where(
                    FleetListingSnapshotRow.item_key == "闲置键盘|19900"
                )
            )
        )
        assert len(history) == 2  # first sight + price change only

    history_resp = await client.get("/api/v1/fleet/listings/history", headers=identity())
    assert history_resp.status_code == 200, history_resp.text
    payload = history_resp.json()
    assert payload["total"] == 3
    keys = {item["itemKey"] for item in payload["items"]}
    assert keys == {"闲置键盘|19900", "机械鼠标|8900", "闲置键盘|17900"}


async def test_real_id_marker_and_empty_screen(api):
    client, _app = api
    device = await create_direct_device(client, "listings-realid")
    auth = await _enroll(client, device, "listings-realid-instance")

    pushed = await _push(client, auth, _screen("run-1", 1, [
        _row("8839217461023749152", title="有真实ID的宝贝", price=5900),
    ]))
    assert pushed.status_code == 201
    empty = await _push(client, auth, _screen("run-1", 2, []))
    assert empty.status_code == 201
    assert empty.json()["accepted"] == 0

    history = await client.get("/api/v1/fleet/listings/history", headers=identity())
    items = history.json()["items"]
    assert len(items) == 1
    assert items[0]["dedupeMarker"] == "REAL_ID"


async def test_tenant_isolation_and_read_only(api):
    client, _app = api
    device = await create_direct_device(client, "listings-iso")
    auth = await _enroll(client, device, "listings-iso-instance")
    pushed = await _push(client, auth, _screen("run-1", 1, [_row("A|100", title="A", price=100)]))
    assert pushed.status_code == 201

    foreign = await client.get("/api/v1/fleet/listings/history", headers=OTHER_TENANT)
    assert foreign.status_code == 200
    assert foreign.json()["total"] == 0
    assert foreign.json()["items"] == []

    # Read-only invariant: pushes never create controlled-step tasks.
    async with _app.state.database.unit_of_work() as session:
        tasks = list(await session.scalars(select(MobileTaskRow)))
    assert tasks == []
