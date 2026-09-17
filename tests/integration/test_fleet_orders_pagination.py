"""O10 (fleet-first-20260916.1): order pagination, dedupe-upsert, checkpoint
binding and history slicing on the fleet layer.

- POST /companion/v2/orders/screens  — per-screen push (page summary + rows):
  cross-page/pinned duplicates, offline replay, empty/partial screens.
- Checkpoint guards (409): account mismatch (设备 A 的订单不归 B 账号), schema
  version mismatch, silent screen gaps, foreign-run resume.
- GET /api/v1/fleet/orders/history — cursor pagination, tenant scoping,
  collection-window + missing-page annotation, dedupe markers.
- Read-only invariant: pushes never create controlled-steps tasks.
"""

from __future__ import annotations

import sqlite3
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from alembic import command
from cloudctl_api import create_app
from cloudctl_api.db import MobileTaskRow
from cloudctl_api.fleet_orders import FleetOrderPageRow
from cloudctl_api.settings import Settings
from fastapi import FastAPI
from test_control_api_migrations import migration_config, table_columns, tables
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


def _order(
    key: str,
    *,
    direction: str = "SOLD",
    title: str = "闲置键盘",
    buyer: str = "buyer_a",
    amount: int | None = 19900,
    status: str = "待发货",
    occurred: str | None = "2026-09-17T10:00:00+00:00",
) -> dict[str, Any]:
    return {
        "direction": direction,
        "order_key": key,
        "item_title": title,
        "buyer_name": buyer,
        "amount_cents": amount,
        "status_text": status,
        "occurred_at": occurred,
        "raw": {"line": f"{title} {buyer} {status}"},
    }


async def _setup_device(client: httpx.AsyncClient, name: str) -> tuple[str, dict[str, str]]:
    device = await create_direct_device(client, name)
    auth = await _enroll(client, device, f"{name}-instance")
    return device, auth


async def _screens(
    client: httpx.AsyncClient,
    auth: dict[str, str],
    *,
    run: str = "run-1",
    account: str = "xianyu-alpha",
    version: int = 1,
    direction: str = "SOLD",
    screen: int = 1,
    rows: list[dict[str, Any]] | None = None,
    partial: list[int] | None = None,
    collected: str | None = "2026-09-17T10:00:05+00:00",
) -> httpx.Response:
    payload: dict[str, Any] = {
        "runKey": run,
        "accountKey": account,
        "schemaVersion": version,
        "screen": screen,
        "direction": direction,
        "rows": rows if rows is not None else [],
    }
    if partial is not None:
        payload["partialRows"] = partial
    if collected is not None:
        payload["collectedAt"] = collected
    return await client.post("/companion/v2/orders/screens", headers=auth, json=payload)


async def _count_pages(app: FastAPI) -> int:
    from sqlalchemy import func, select

    async with app.state.database.unit_of_work() as session:
        return int(await session.scalar(select(func.count()).select_from(FleetOrderPageRow)) or 0)


# ---------------------------------------------------------------------------
# Migration 20260917_0026 (up/down round trip on SQLite)
# ---------------------------------------------------------------------------


def test_fleet_orders_migration_up_down_roundtrip(tmp_path: Path) -> None:
    database_path = tmp_path / "fleet-orders-migrations.db"
    config = migration_config(database_path)

    command.upgrade(config, "20260917_0025")
    with sqlite3.connect(database_path) as connection:
        assert "fleet_order_page" not in tables(connection)
        assert "fleet_order_checkpoint" not in tables(connection)

    command.upgrade(config, "head")
    with sqlite3.connect(database_path) as connection:
        assert {
            "id", "tenant_id", "device_id", "platform", "direction", "account_key",
            "run_key", "screen", "rows_seen", "new_keys", "updated_keys", "overlap",
            "partial_rows", "empty_page", "collected_at", "created_at",
        } == table_columns(connection, "fleet_order_page")
        assert {
            "id", "tenant_id", "device_id", "platform", "direction", "account_key",
            "schema_version", "run_key", "last_screen", "seen_keys", "created_at",
            "updated_at",
        } == table_columns(connection, "fleet_order_checkpoint")
        connection.execute(
            """
            INSERT INTO fleet_order_page (
                id, tenant_id, device_id, platform, direction, account_key, run_key,
                screen, rows_seen, new_keys, updated_keys, overlap, partial_rows,
                empty_page, collected_at, created_at
            ) VALUES (
                '00000000-0000-7000-8000-00000000b001',
                '00000000-0000-7000-8000-00000000b002',
                '00000000-0000-7000-8000-00000000b003',
                'xianyu', 'SOLD', 'xianyu-alpha', 'run-1',
                1, 2, 2, 0, 0, 0, 0,
                '2026-09-17 10:00:05+00:00', '2026-09-17 10:00:05+00:00'
            )
            """
        )
        connection.commit()
        # (tenant, device, run, screen) unique: an offline replay stores one page.
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO fleet_order_page (
                    id, tenant_id, device_id, platform, direction, account_key, run_key,
                    screen, rows_seen, new_keys, updated_keys, overlap, partial_rows,
                    empty_page, created_at
                ) VALUES (
                    '00000000-0000-7000-8000-00000000b004',
                    '00000000-0000-7000-8000-00000000b002',
                    '00000000-0000-7000-8000-00000000b003',
                    'xianyu', 'SOLD', 'xianyu-alpha', 'run-1',
                    1, 2, 2, 0, 0, 0, 0, '2026-09-17 10:00:06+00:00'
                )
                """
            )
            connection.commit()
        connection.rollback()
        for statement in (
            "UPDATE fleet_order_page SET direction = 'REFUNDED' WHERE id = '00000000-0000-7000-8000-00000000b001'",
            "UPDATE fleet_order_page SET screen = 0 WHERE id = '00000000-0000-7000-8000-00000000b001'",
            "UPDATE fleet_order_page SET platform = 'taobao' WHERE id = '00000000-0000-7000-8000-00000000b001'",
        ):
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(statement)
            connection.rollback()

    command.downgrade(config, "20260917_0025")
    with sqlite3.connect(database_path) as connection:
        assert "fleet_order_page" not in tables(connection)
        assert "fleet_order_checkpoint" not in tables(connection)

    command.upgrade(config, "head")


# ---------------------------------------------------------------------------
# Per-screen push: dedupe, overlap, replay
# ---------------------------------------------------------------------------


async def test_push_screens_flow_with_cross_page_and_pinned_overlap(api):
    client, app = api
    device, auth = await _setup_device(client, "fleet-orders-dev")
    first = await _screens(
        client, auth, screen=1, rows=[_order("k1"), _order("k2")],
        collected="2026-09-17T10:00:05+00:00",
    )
    assert first.status_code == 201, first.text
    body = first.json()
    assert body["accepted"] == 2
    assert body["duplicates"] == 0
    assert body["replayed"] is False
    assert body["checkpoint"]["lastScreen"] == 1
    assert body["checkpoint"]["seenKeys"] == 2

    # 跨页重复 + 置顶：k2/k1 重现，只有 k3 是新键。
    second = await _screens(
        client, auth, screen=2, rows=[_order("k2"), _order("k1"), _order("k3")],
        collected="2026-09-17T10:00:20+00:00",
    )
    assert second.status_code == 201, second.text
    assert second.json()["accepted"] == 1
    assert second.json()["duplicates"] == 2
    assert second.json()["checkpoint"]["lastScreen"] == 2

    # 断网重传：同一屏重放 → 200 + replayed，不重复计数。
    replay = await _screens(
        client, auth, screen=2, rows=[_order("k2"), _order("k1"), _order("k3")],
        collected="2026-09-17T10:00:35+00:00",
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["replayed"] is True
    assert replay.json()["accepted"] == 0
    assert await _count_pages(app) == 2

    history = (await client.get("/api/v1/fleet/orders/history", headers=identity())).json()
    assert history["total"] == 3
    (window,) = history["windows"]
    assert window["runKey"] == "run-1"
    assert window["accountKey"] == "xianyu-alpha"
    assert window["screensPresent"] == [1, 2]
    assert window["missingScreens"] == []
    assert window["newKeys"] == 3
    assert window["overlap"] == 2
    assert window["startedAt"] is not None
    assert window["endedAt"] is not None


async def test_empty_partial_and_missing_screens_annotate_the_window(api):
    client, app = api
    device, auth = await _setup_device(client, "fleet-orders-window")
    partial = await _screens(client, auth, screen=1, rows=[_order("k1")], partial=[0])
    assert partial.status_code == 201, partial.text
    empty = await _screens(client, auth, screen=2, rows=[])
    assert empty.status_code == 201, empty.text
    assert empty.json()["accepted"] == 0

    history = (await client.get("/api/v1/fleet/orders/history", headers=identity())).json()
    (window,) = history["windows"]
    assert window["emptyScreens"] == [2]
    assert window["partialScreens"] == [1]

    # 屏号断档（如并发重试风暴漏推第 3 屏）：历史必须标注缺失页。
    from datetime import datetime

    from sqlalchemy import select

    async with app.state.database.unit_of_work() as session:
        existing = (
            await session.scalars(select(FleetOrderPageRow).order_by(FleetOrderPageRow.screen))
        ).first()
        assert existing is not None
        session.add(
            FleetOrderPageRow(
                id="00000000-0000-7000-8000-00000000c003",
                tenant_id=existing.tenant_id,
                device_id=existing.device_id,
                platform="xianyu",
                direction="SOLD",
                account_key="xianyu-alpha",
                run_key="run-1",
                screen=4,
                rows_seen=1,
                new_keys=1,
                updated_keys=0,
                overlap=0,
                partial_rows=0,
                empty_page=False,
                created_at=datetime(2026, 9, 17, 10, 1, 0),
            )
        )
    history = (await client.get("/api/v1/fleet/orders/history", headers=identity())).json()
    (window,) = history["windows"]
    assert window["screensPresent"] == [1, 2, 4]
    assert window["missingScreens"] == [3]


async def test_status_change_upserts_and_dedupe_markers(api):
    client, _app = api
    device, auth = await _setup_device(client, "fleet-orders-upsert")
    first = await _screens(client, auth, screen=1, rows=[_order("k1", status="待发货")])
    assert first.status_code == 201, first.text

    # 同键状态变化 → upsert（slice1 的首写保持语义在此升级）。
    changed = await _screens(client, auth, screen=2, rows=[_order("k1", status="已发货")])
    assert changed.status_code == 201, changed.text
    assert changed.json()["updated"] == 1
    assert changed.json()["accepted"] == 0

    # 真实可见订单号键 → REAL_ID；复合键 → MISSING_ID 降级标记（不拼凑假 ID）。
    real = await _screens(
        client, auth, screen=3, rows=[_order("371234567890123456", status="交易成功")]
    )
    assert real.status_code == 201, real.text

    history = (await client.get("/api/v1/fleet/orders/history", headers=identity())).json()
    by_key = {item["orderKey"]: item for item in history["items"]}
    assert by_key["k1"]["statusText"] == "已发货"
    assert by_key["k1"]["dedupeMarker"] == "MISSING_ID"
    assert by_key["371234567890123456"]["dedupeMarker"] == "REAL_ID"
    assert history["dedupeMarkers"] == {"realId": 1, "missingId": 1}

    # 状态回退为空不算变化（页面没显示状态 ≠ 状态被清除）。
    blank = await _screens(
        client, auth, screen=2, rows=[_order("k1", status="已发货")]
    )
    assert blank.status_code == 200, blank.text
    assert blank.json()["duplicates"] == 1


async def test_null_field_fill_counts_as_upsert(api):
    client, _app = api
    device, auth = await _setup_device(client, "fleet-orders-fill")
    # 第 1 屏没读到时间（occurred=None 落库）；第 2 屏补上了 → upsert。
    first = await _screens(
        client, auth, screen=1, rows=[_order("k1", occurred=None)]
    )
    assert first.status_code == 201, first.text
    filled = await _screens(
        client, auth, screen=2, rows=[_order("k1", occurred="2026-09-17T09:00:00+00:00")]
    )
    assert filled.status_code == 201, filled.text
    assert filled.json()["updated"] == 1
    history = (await client.get("/api/v1/fleet/orders/history", headers=identity())).json()
    assert history["items"][0]["occurredAt"] is not None


# ---------------------------------------------------------------------------
# Checkpoint binding: account + version + run + screen guards
# ---------------------------------------------------------------------------


async def test_checkpoint_account_version_run_and_gap_guards(api):
    client, _app = api
    device, auth = await _setup_device(client, "fleet-orders-cp")

    start = await _screens(client, auth, run="run-A", account="xianyu-alpha", screen=1, rows=[_order("k1")])
    assert start.status_code == 201, start.text

    # A 设备订单不归 B 账号：别人的 run 换账号续推（任意屏号）→ 409。
    for screen in (1, 2):
        foreign = await _screens(
            client, auth, run="run-A", account="xianyu-beta", screen=screen, rows=[_order("k9")]
        )
        assert foreign.status_code == 409, foreign.text
        assert "another account" in foreign.text

    # 新 run 从第 1 屏开始 → 允许，断点重绑。
    rebind = await _screens(
        client, auth, run="run-B", account="xianyu-beta", screen=1, rows=[_order("k2")]
    )
    assert rebind.status_code == 201, rebind.text
    assert rebind.json()["checkpoint"]["runKey"] == "run-B"

    second = await _screens(client, auth, run="run-B", account="xianyu-beta", screen=2, rows=[_order("k3")])
    assert second.status_code == 201, second.text

    # 版本不匹配 → 409：旧断点的语义不可信。
    versioned = await _screens(
        client, auth, run="run-B", account="xianyu-beta", version=2, screen=3, rows=[_order("k4")]
    )
    assert versioned.status_code == 409, versioned.text
    assert "schema version" in versioned.text

    # 屏号跳跃 → 409：缺失页不允许被默默跳过。
    gap = await _screens(client, auth, run="run-B", account="xianyu-beta", screen=4, rows=[_order("k4")])
    assert gap.status_code == 409, gap.text
    assert "screen gap" in gap.text

    # 换 run 但不从第 1 屏开始 → 409。
    foreign_run = await _screens(
        client, auth, run="run-C", account="xianyu-beta", screen=2, rows=[_order("k5")]
    )
    assert foreign_run.status_code == 409, foreign_run.text

    # 断点查询：绑定信息如实返回；另一方向没有断点 → 404。
    checkpoint = await client.get(
        "/companion/v2/orders/checkpoint", headers=auth, params={"direction": "SOLD"}
    )
    assert checkpoint.status_code == 200, checkpoint.text
    payload = checkpoint.json()
    assert payload["runKey"] == "run-B"
    assert payload["accountKey"] == "xianyu-beta"
    assert payload["lastScreen"] == 2
    assert payload["schemaVersion"] == 1
    missing = await client.get(
        "/companion/v2/orders/checkpoint", headers=auth, params={"direction": "BOUGHT"}
    )
    assert missing.status_code == 404, missing.text
    bad_direction = await client.get(
        "/companion/v2/orders/checkpoint", headers=auth, params={"direction": "REFUNDED"}
    )
    assert bad_direction.status_code == 422, bad_direction.text


async def test_history_account_filter_does_not_leak_other_account(api):
    client, _app = api
    device, auth = await _setup_device(client, "fleet-orders-accounts")
    await _screens(client, auth, run="run-A", account="xianyu-alpha", screen=1, rows=[_order("k1")])
    await _screens(client, auth, run="run-B", account="xianyu-beta", screen=1, rows=[_order("k2")])

    alpha = (
        await client.get(
            "/api/v1/fleet/orders/history", headers=identity(), params={"account_key": "xianyu-alpha"}
        )
    ).json()
    assert [w["accountKey"] for w in alpha["windows"]] == ["xianyu-alpha"]
    beta = (
        await client.get(
            "/api/v1/fleet/orders/history", headers=identity(), params={"account_key": "xianyu-beta"}
        )
    ).json()
    assert [w["accountKey"] for w in beta["windows"]] == ["xianyu-beta"]
    # 订单行是设备维度的观测事实（不按账号过滤）；窗口归属按账号隔离，
    # gamma 账号查不到任何窗口——A 账号采的窗口绝不归到别的账号名下。
    nobody = (
        await client.get(
            "/api/v1/fleet/orders/history", headers=identity(), params={"account_key": "xianyu-gamma"}
        )
    ).json()
    assert nobody["windows"] == []


# ---------------------------------------------------------------------------
# History: cursor pagination + tenant isolation + read-only invariant
# ---------------------------------------------------------------------------


async def test_history_cursor_pagination_and_validation(api):
    client, _app = api
    device, auth = await _setup_device(client, "fleet-orders-pages")
    # 25 单分 3 屏（每屏上限 20 行）。
    rows_screen1 = [_order(f"page-1-{n}", occurred=f"2026-09-17T0{n % 10}:00:00+00:00") for n in range(10)]
    rows_screen2 = [_order(f"page-2-{n}") for n in range(10)]
    rows_screen3 = [_order(f"page-3-{n}") for n in range(5)]
    await _screens(client, auth, screen=1, rows=rows_screen1)
    await _screens(client, auth, screen=2, rows=rows_screen2)
    await _screens(client, auth, screen=3, rows=rows_screen3)

    page1 = (
        await client.get("/api/v1/fleet/orders/history", headers=identity(), params={"limit": 10})
    ).json()
    assert page1["total"] == 25
    assert len(page1["items"]) == 10
    assert "nextCursor" in page1

    page2 = (
        await client.get(
            "/api/v1/fleet/orders/history",
            headers=identity(),
            params={"limit": 10, "cursor": page1["nextCursor"]},
        )
    ).json()
    assert page2["offset"] == 10
    assert len(page2["items"]) == 10
    assert "nextCursor" in page2
    assert {item["id"] for item in page1["items"]}.isdisjoint({item["id"] for item in page2["items"]})

    page3 = (
        await client.get(
            "/api/v1/fleet/orders/history",
            headers=identity(),
            params={"limit": 10, "cursor": page2["nextCursor"]},
        )
    ).json()
    assert page3["offset"] == 20
    assert len(page3["items"]) == 5
    assert "nextCursor" not in page3

    for bad in ("%%%", "not-a-cursor", "eyJ2IjoyfQ"):
        invalid = await client.get(
            "/api/v1/fleet/orders/history",
            headers=identity(),
            params={"cursor": bad},
        )
        assert invalid.status_code == 422, invalid.text
    over = await client.get(
        "/api/v1/fleet/orders/history", headers=identity(), params={"limit": 101}
    )
    assert over.status_code == 422, over.text
    bad_direction = await client.get(
        "/api/v1/fleet/orders/history", headers=identity(), params={"direction": "REFUNDED"}
    )
    assert bad_direction.status_code == 422, bad_direction.text


async def test_history_tenant_isolation_and_read_only_push(api):
    client, app = api
    device, auth = await _setup_device(client, "fleet-orders-tenant")
    pushed = await _screens(client, auth, screen=1, rows=[_order("k1"), _order("k2")])
    assert pushed.status_code == 201, pushed.text

    # 跨租户：列表/窗口都空，绝不泄漏。
    foreign = await client.get("/api/v1/fleet/orders/history", headers=OTHER_TENANT)
    assert foreign.status_code == 200, foreign.text
    assert foreign.json()["total"] == 0
    assert foreign.json()["items"] == []
    assert foreign.json()["windows"] == []

    # 只读同步：推送不创建任何 controlled-steps 任务（无发货/评价/交易写动作）。
    from sqlalchemy import func, select

    async with app.state.database.unit_of_work() as session:
        tasks = int(await session.scalar(select(func.count()).select_from(MobileTaskRow)) or 0)
    assert tasks == 0


async def test_push_validation_and_auth_gates(api):
    client, _app = api
    device, auth = await _setup_device(client, "fleet-orders-validate")

    anonymous = await client.post(
        "/companion/v2/orders/screens",
        json={"runKey": "r", "accountKey": "a", "schemaVersion": 1, "screen": 1, "direction": "SOLD"},
    )
    assert anonymous.status_code == 401, anonymous.text

    bad_bodies = [
        {"runKey": "", "accountKey": "a", "schemaVersion": 1, "screen": 1, "direction": "SOLD"},
        {"runKey": "r", "accountKey": "a", "schemaVersion": 0, "screen": 1, "direction": "SOLD"},
        {"runKey": "r", "accountKey": "a", "schemaVersion": 1, "screen": 0, "direction": "SOLD"},
        {"runKey": "r", "accountKey": "a", "schemaVersion": 1, "screen": 51, "direction": "SOLD"},
        {"runKey": "r", "accountKey": "a", "schemaVersion": 1, "screen": 1, "direction": "REFUNDED"},
        {
            "runKey": "r", "accountKey": "a", "schemaVersion": 1, "screen": 1,
            "direction": "SOLD", "rows": [_order(f"bulk-{n}") for n in range(21)],
        },
        {
            "runKey": "r", "accountKey": "a", "schemaVersion": 1, "screen": 1,
            "direction": "SOLD", "rows": [{**_order("k"), "order_key": "   "}],
        },
        {
            "runKey": "r", "accountKey": "a", "schemaVersion": 1, "screen": 1,
            "direction": "SOLD", "rows": [], "extra": 1,
        },
    ]
    for index, payload in enumerate(bad_bodies):
        response = await client.post("/companion/v2/orders/screens", headers=auth, json=payload)
        assert response.status_code == 422, f"{index}: {response.text}"
