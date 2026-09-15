"""Order sync slice 1 (order-sync/20260915.1): table migration, companion push,
operator query, and the frozen xianyu.collect_orders.steps.v1 orchestration."""

from __future__ import annotations

import sqlite3
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from alembic import command
from cloudctl_api import create_app
from cloudctl_api.db import MobileTaskRow
from cloudctl_api.settings import Settings
from fastapi import FastAPI
from test_control_api_migrations import migration_config, table_columns, tables
from test_platform_tasks import _enroll, create_direct_device, identity

XIANYU = "com.taobao.idlefish"
COLLECT_COMMAND = "xianyu.collect_orders.steps.v1"
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
    occurred: str | None = "2026-09-15T10:00:00+00:00",
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


async def _push(
    client: httpx.AsyncClient,
    auth: dict[str, str],
    orders: list[dict[str, Any]],
    collected_at: str = "2026-09-15T10:00:05+00:00",
) -> httpx.Response:
    return await client.post(
        "/companion/v2/orders/batch",
        headers=auth,
        json={"orders": orders, "collected_at": collected_at},
    )


async def _setup_device(client: httpx.AsyncClient, name: str) -> tuple[str, dict[str, str]]:
    device = await create_direct_device(client, name)
    auth = await _enroll(client, device, f"{name}-instance")
    return device, auth


# ---------------------------------------------------------------------------
# Migration 20260915_0021 (up/down round trip on SQLite)
# ---------------------------------------------------------------------------


def test_orders_migration_up_down_roundtrip(tmp_path: Path) -> None:
    database_path = tmp_path / "orders-migrations.db"
    config = migration_config(database_path)

    command.upgrade(config, "20260915_0020")
    with sqlite3.connect(database_path) as connection:
        assert "xianyu_order" not in tables(connection)

    command.upgrade(config, "head")
    with sqlite3.connect(database_path) as connection:
        assert {
            "id",
            "tenant_id",
            "device_id",
            "platform",
            "direction",
            "order_key",
            "item_title",
            "buyer_name",
            "amount_cents",
            "status_text",
            "occurred_at",
            "raw",
            "created_at",
            "updated_at",
        } == table_columns(connection, "xianyu_order")
        connection.execute(
            """
            INSERT INTO xianyu_order (
                id, tenant_id, device_id, platform, direction, order_key,
                item_title, buyer_name, amount_cents, status_text,
                occurred_at, raw, created_at, updated_at
            ) VALUES (
                '00000000-0000-7000-8000-00000000a001',
                '00000000-0000-7000-8000-00000000a002',
                '00000000-0000-7000-8000-00000000a003',
                'xianyu', 'SOLD', 'order-1',
                '闲置键盘', 'buyer_a', 19900, '待发货',
                '2026-09-15 10:00:00+00:00', '{}',
                '2026-09-15 10:00:05+00:00', '2026-09-15 10:00:05+00:00'
            )
            """
        )
        connection.commit()
        # Natural-key uniqueness.
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO xianyu_order (
                    id, tenant_id, device_id, platform, direction, order_key,
                    created_at, updated_at
                ) VALUES (
                    '00000000-0000-7000-8000-00000000a004',
                    '00000000-0000-7000-8000-00000000a002',
                    '00000000-0000-7000-8000-00000000a003',
                    'xianyu', 'SOLD', 'order-1',
                    '2026-09-15 10:00:06+00:00', '2026-09-15 10:00:06+00:00'
                )
            """
            )
            connection.commit()
        connection.rollback()
        # Platform / direction / amount check constraints.
        for statement in (
            "UPDATE xianyu_order SET platform = 'taobao' WHERE order_key = 'order-1'",
            "UPDATE xianyu_order SET direction = 'REFUNDED' WHERE order_key = 'order-1'",
            "UPDATE xianyu_order SET amount_cents = 0 WHERE order_key = 'order-1'",
        ):
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(statement)
            connection.rollback()

    command.downgrade(config, "20260915_0020")
    with sqlite3.connect(database_path) as connection:
        assert "xianyu_order" not in tables(connection)

    command.upgrade(config, "head")


# ---------------------------------------------------------------------------
# Companion batch push (idempotent, first snapshot wins)
# ---------------------------------------------------------------------------


async def test_companion_batch_ingest_is_idempotent(api):
    client, _app = api
    device, auth = await _setup_device(client, "orders-dev")
    first = await _push(client, auth, [_order("order-1"), _order("order-2")])
    assert first.status_code == 201, first.text
    assert first.json() == {"accepted": 2, "duplicates": 0}

    replay = await _push(client, auth, [_order("order-1"), _order("order-2")])
    assert replay.status_code == 200, replay.text
    assert replay.json() == {"accepted": 0, "duplicates": 2}

    # Mixed batch: one unseen row lands, the replayed row is skipped.
    mixed = await _push(
        client, auth, [_order("order-1", title="改标题也不覆盖"), _order("order-3")]
    )
    assert mixed.status_code == 201, mixed.text
    assert mixed.json() == {"accepted": 1, "duplicates": 1}

    listed = (await client.get("/api/v1/orders", headers=identity())).json()
    assert listed["total"] == 3
    # First write wins: the snapshot keeps the original item_title.
    by_key = {item["orderKey"]: item for item in listed["items"]}
    assert by_key["order-1"]["itemTitle"] == "闲置键盘"

    # The same natural key on another device is a different order.
    device2, auth2 = await _setup_device(client, "orders-dev-2")
    cross = await _push(client, auth2, [_order("order-1")])
    assert cross.status_code == 201, cross.text
    assert cross.json() == {"accepted": 1, "duplicates": 0}
    assert (await client.get("/api/v1/orders", headers=identity())).json()["total"] == 4


async def test_companion_batch_requires_binding_auth(api):
    client, _app = api
    anonymous = await _push(client, {}, [_order("order-x")])
    assert anonymous.status_code == 401, anonymous.text


@pytest.mark.parametrize(
    "payload,marker",
    [
        ({"orders": [], "collected_at": "2026-09-15T10:00:05+00:00"}, "orders"),
        (
            {"orders": [_order(f"order-bulk-{n}") for n in range(21)]},
            "orders",
        ),
        (
            {
                "orders": [
                    {
                        "direction": "SOLD",
                        "order_key": "   ",
                        "item_title": "x",
                        "buyer_name": "b",
                        "amount_cents": 1,
                        "status_text": "s",
                    }
                ]
            },
            "orders.0.order_key",
        ),
        ({"orders": [{"direction": "SOLD", "order_key": "k"}], "extra": 1}, "extra"),
        ({"orders": [{"order_key": "k"}]}, "direction"),
        ({"orders": [{"direction": "REFUNDED", "order_key": "k"}]}, "direction"),
        ({"orders": [{"direction": "SOLD", "order_key": "k", "amount_cents": 0}]}, "amount_cents"),
        (
            {"orders": [{"direction": "SOLD", "order_key": "k", "amount_cents": -5}]},
            "amount_cents",
        ),
        (
            {"orders": [{"direction": "SOLD", "order_key": "k", "occurred_at": 12345}]},
            "occurred_at",
        ),
    ],
)
async def test_companion_batch_row_validation(api, payload, marker):
    client, _app = api
    device, auth = await _setup_device(client, "orders-validate")
    response = await client.post("/companion/v2/orders/batch", headers=auth, json=payload)
    assert response.status_code == 422, response.text
    assert marker in response.text
    listed = (await client.get("/api/v1/orders", headers=identity())).json()
    assert listed["total"] == 0


async def test_occurred_at_parse_failure_stores_null(api):
    client, _app = api
    device, auth = await _setup_device(client, "orders-time")
    # Page time text that is not ISO: the row is still an observed fact, the
    # timestamp becomes NULL (contract §2 解析失败则空).
    accepted = await _push(client, auth, [_order("order-notime", occurred="3天前")])
    assert accepted.status_code == 201, accepted.text
    items = (await client.get("/api/v1/orders", headers=identity())).json()["items"]
    assert items[0]["occurredAt"] is None
    # An explicit null stays null; a valid ISO string is parsed.
    ok = await _push(client, auth, [_order("order-nulltime", occurred=None)])
    assert ok.status_code == 201, ok.text
    parsed = await _push(client, auth, [_order("order-z", occurred="2026-09-15T08:00:00Z")])
    assert parsed.status_code == 201, parsed.text
    by_key = {
        item["orderKey"]: item
        for item in (await client.get("/api/v1/orders", headers=identity())).json()["items"]
    }
    assert by_key["order-nulltime"]["occurredAt"] is None
    assert by_key["order-z"]["occurredAt"] is not None


# ---------------------------------------------------------------------------
# Operator query API
# ---------------------------------------------------------------------------


async def test_operator_list_filters_pagination_and_ordering(api):
    client, _app = api
    device, auth = await _setup_device(client, "orders-query")
    when = datetime(2026, 9, 15, 10, 0, 0, tzinfo=UTC)
    rows = [
        _order("sold-1", occurred=(when).isoformat(), status="待发货"),
        _order("sold-2", occurred=(when + timedelta(hours=1)).isoformat(), status="已发货"),
        _order(
            "bought-1",
            direction="BOUGHT",
            occurred=(when + timedelta(hours=2)).isoformat(),
            status="交易成功",
        ),
        _order("sold-notime", occurred=None, status="待发货"),
    ]
    pushed = await _push(client, auth, rows)
    assert pushed.status_code == 201, pushed.text

    everything = (await client.get("/api/v1/orders", headers=identity())).json()
    assert everything["total"] == 4
    # occurred_at DESC with NULLs last; ties fall back to created_at DESC.
    assert [item["orderKey"] for item in everything["items"]] == [
        "bought-1",
        "sold-2",
        "sold-1",
        "sold-notime",
    ]

    by_direction = (
        await client.get("/api/v1/orders", headers=identity(), params={"direction": "SOLD"})
    ).json()
    assert by_direction["total"] == 3

    by_status = (
        await client.get("/api/v1/orders", headers=identity(), params={"status_text": "待发货"})
    ).json()
    assert {item["orderKey"] for item in by_status["items"]} == {"sold-1", "sold-notime"}

    by_device = (
        await client.get("/api/v1/orders", headers=identity(), params={"device_id": device})
    ).json()
    assert by_device["total"] == 4
    other_device = (
        await client.get(
            "/api/v1/orders",
            headers=identity(),
            params={"device_id": "00000000-0000-7000-8000-0000000000f1"},
        )
    ).json()
    assert other_device["total"] == 0

    page = (
        await client.get("/api/v1/orders", headers=identity(), params={"limit": 2, "offset": 1})
    ).json()
    assert page["total"] == 4
    assert [item["orderKey"] for item in page["items"]] == ["sold-2", "sold-1"]

    invalid = await client.get("/api/v1/orders", headers=identity(), params={"limit": 101})
    assert invalid.status_code == 422, invalid.text


async def test_operator_detail_includes_raw_and_isolation(api):
    client, _app = api
    device, auth = await _setup_device(client, "orders-detail")
    await _push(client, auth, [_order("order-detail")])
    listed = (await client.get("/api/v1/orders", headers=identity())).json()
    order_id = listed["items"][0]["id"]

    detail = await client.get(f"/api/v1/orders/{order_id}", headers=identity())
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["orderKey"] == "order-detail"
    assert body["raw"] == {"line": "闲置键盘 buyer_a 待发货"}
    assert "raw" not in listed["items"][0]

    missing = await client.get(
        "/api/v1/orders/00000000-0000-7000-8000-0000000000ff", headers=identity()
    )
    assert missing.status_code == 404, missing.text
    # Tenant isolation: another tenant sees nothing.
    foreign_list = await client.get("/api/v1/orders", headers=OTHER_TENANT)
    assert foreign_list.status_code == 200
    assert foreign_list.json()["total"] == 0
    foreign_detail = await client.get(f"/api/v1/orders/{order_id}", headers=OTHER_TENANT)
    assert foreign_detail.status_code == 404, foreign_detail.text


# ---------------------------------------------------------------------------
# Collection orchestration (xianyu.collect_orders.steps.v1)
# ---------------------------------------------------------------------------


async def _collect(
    client: httpx.AsyncClient,
    device: str,
    key: str,
    *,
    direction: str = "SOLD",
    max_rows: int = 5,
    role: str = "device_operator",
) -> httpx.Response:
    return await client.post(
        "/api/v1/xianyu/orders:collect",
        headers={**identity(role=role), "Idempotency-Key": key},
        json={"device_id": device, "direction": direction, "max_rows": max_rows},
    )


async def test_collect_run_shape_and_idempotency(api):
    client, app = api
    device = await create_direct_device(client, "orders-collect")
    first = await _collect(client, device, "collect-key-1")
    assert first.status_code == 201, first.text
    body = first.json()
    assert body["commandType"] == COLLECT_COMMAND
    assert body["direction"] == "SOLD"
    assert body["maxRows"] == 5
    assert body["targetCount"] == 1
    run_id = body["runId"]
    task_id = body["taskIds"][0]

    # Frozen steps shape in storage; the header never carries an action key.
    async with app.state.database.unit_of_work() as session:
        row = await session.get(MobileTaskRow, task_id)
        assert row is not None
        assert row.command_type == COLLECT_COMMAND
        assert row.batch_id == run_id
        header, *steps = row.steps
        assert "action" not in header
        assert header["orderCollection"] == {
            "runId": run_id,
            "direction": "SOLD",
            "maxRows": 5,
            "commandType": COLLECT_COMMAND,
        }
        assert [step["action"] for step in steps] == [
            "ui.tap",
            "ui.tap",
            "ui.readOrders",
            "ui.screenshot",
            "run.log",
        ]
        read = steps[2]
        assert read["direction"] == "SOLD"
        assert read["maxRows"] == 5
        assert read["locatorRef"] == "xianyu_orders_container"
        assert steps[1]["locatorRef"] == "xianyu_order_list_sold"
        assert steps[4]["messageCode"] == "XIANYU_COLLECT_ORDERS_DONE"
        # Steps hash invariant: metadata header does not change the hashed body.
        hashed = [step for step in row.steps if step.get("action")]
        assert len(hashed) == 5

    replay = await _collect(client, device, "collect-key-1")
    assert replay.status_code == 200, replay.text
    assert replay.headers["Idempotency-Replayed"] == "true"
    assert replay.json()["runId"] == run_id
    assert replay.json()["taskIds"] == [task_id]

    summary = await client.get(f"/api/v1/xianyu/orders/runs/{run_id}", headers=identity())
    assert summary.status_code == 200, summary.text
    payload = summary.json()
    assert payload["taskCount"] == 1
    assert payload["summary"] == {"QUEUED": 1}
    assert payload["allTerminal"] is False
    assert payload["tasks"][0]["direction"] == "SOLD"
    assert payload["commandType"] == COLLECT_COMMAND

    missing = await client.get(
        "/api/v1/xianyu/orders/runs/00000000-0000-7000-8000-0000000000ee",
        headers=identity(),
    )
    assert missing.status_code == 404, missing.text
    viewer = await client.get(
        f"/api/v1/xianyu/orders/runs/{run_id}", headers=identity(role="viewer")
    )
    assert viewer.status_code == 200, viewer.text

    # The companion claims one read-only task and sees the frozen payload.
    auth = await _enroll(client, device, "orders-collect-instance")
    claimed = await client.post(
        "/companion/v2/tasks/claim", headers=auth, json={"leaseSeconds": 60}
    )
    assert claimed.status_code == 200, claimed.text
    claimed_body = claimed.json()
    assert claimed_body["taskId"] == task_id
    assert claimed_body["commandType"] == COLLECT_COMMAND
    reads = [step for step in claimed_body["steps"] if step.get("action") == "ui.readOrders"]
    assert len(reads) == 1
    assert reads[0]["maxRows"] == 5


async def test_collect_bought_direction_uses_bought_entry(api):
    client, _app = api
    device = await create_direct_device(client, "orders-collect-b")
    response = await _collect(client, device, "collect-bought", direction="BOUGHT", max_rows=10)
    assert response.status_code == 201, response.text
    async with _app.state.database.unit_of_work() as session:
        row = await session.get(MobileTaskRow, response.json()["taskIds"][0])
        # steps[0] is the run metadata header (no action key); real steps follow.
        open_entry, read = row.steps[2], row.steps[3]
        assert open_entry["locatorRef"] == "xianyu_order_list_bought"
        assert read["direction"] == "BOUGHT"
        assert read["maxRows"] == 10


async def test_collect_permission_and_validation_gates(api):
    client, _app = api
    device = await create_direct_device(client, "orders-collect-gates")
    denied = await _collect(client, device, "collect-denied", role="viewer")
    assert denied.status_code == 403, denied.text

    unknown = await _collect(client, "00000000-0000-7000-8000-0000000000d1", "collect-unknown")
    assert unknown.status_code == 404, unknown.text

    no_key = await client.post(
        "/api/v1/xianyu/orders:collect",
        headers=identity(),
        json={"device_id": device, "direction": "SOLD", "max_rows": 5},
    )
    assert no_key.status_code == 422, no_key.text

    bad_bodies = [
        {"device_id": device, "direction": "REFUNDED", "max_rows": 5},
        {"device_id": device, "direction": "SOLD", "max_rows": 11},
        {"device_id": device, "direction": "SOLD", "max_rows": 0},
        {"device_id": device, "direction": "SOLD"},
    ]
    for index, payload in enumerate(bad_bodies):
        response = await client.post(
            "/api/v1/xianyu/orders:collect",
            headers={**identity(), "Idempotency-Key": f"collect-bad-{index}"},
            json=payload,
        )
        assert response.status_code == 422, response.text


# ---------------------------------------------------------------------------
# Creation gate: ui.readOrders tasks must match the frozen shape exactly
# ---------------------------------------------------------------------------


def _raw_collect_steps(direction: str = "SOLD", max_rows: int = 5) -> list[dict[str, Any]]:
    entry = "xianyu_order_list_sold" if direction == "SOLD" else "xianyu_order_list_bought"
    return [
        {
            "stepId": "open-profile",
            "action": "ui.tap",
            "locatorRef": "xianyu_profile_tab",
            "timeoutMs": 8_000,
        },
        {"stepId": "open-order-list", "action": "ui.tap", "locatorRef": entry, "timeoutMs": 8_000},
        {
            "stepId": "read-orders",
            "action": "ui.readOrders",
            "locatorRef": "xianyu_orders_container",
            "direction": direction,
            "maxRows": max_rows,
            "timeoutMs": 20_000,
        },
        {
            "stepId": "capture-xianyu_collect_orders",
            "action": "ui.screenshot",
            "label": "xianyu_collect_orders",
            "timeoutMs": 10_000,
        },
        {
            "stepId": "mark-done",
            "action": "run.log",
            "level": "INFO",
            "messageCode": "XIANYU_COLLECT_ORDERS_DONE",
            "timeoutMs": 1_000,
        },
    ]


async def _create_raw_task(
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


async def test_readorders_shape_gate(api):
    client, app = api
    device = await create_direct_device(client, "orders-shape-gate")
    valid = await _create_raw_task(client, device, _raw_collect_steps(), "shape-ok")
    assert valid.status_code == 201, valid.text
    async with app.state.database.unit_of_work() as session:
        row = await session.get(MobileTaskRow, valid.json()["taskId"])
        assert row.command_type == COLLECT_COMMAND

    mutations: dict[str, Callable[[], list[dict[str, Any]]]] = {
        "read_twice": lambda: [
            *_raw_collect_steps()[:3],
            {**_raw_collect_steps()[2], "stepId": "read-orders-again"},
            *_raw_collect_steps()[3:],
        ],
        "missing_screenshot": lambda: _raw_collect_steps()[:3] + [_raw_collect_steps()[4]],
        "wrong_container": lambda: [
            *(_raw_collect_steps()[:2]),
            {**_raw_collect_steps()[2], "locatorRef": "xianyu_messages_tab"},
            *_raw_collect_steps()[3:],
        ],
        "wrong_entry_for_direction": lambda: [
            *(_raw_collect_steps()[:1]),
            {**_raw_collect_steps()[1], "locatorRef": "xianyu_order_list_bought"},
            *_raw_collect_steps()[2:],
        ],
        "extra_tap": lambda: [
            *_raw_collect_steps()[:2],
            {
                "stepId": "detour",
                "action": "ui.tap",
                "locatorRef": "xianyu_messages_tab",
                "timeoutMs": 8_000,
            },
            *_raw_collect_steps()[2:],
        ],
        "wrong_log_code": lambda: [
            *_raw_collect_steps()[:4],
            {**_raw_collect_steps()[4], "messageCode": "XIANYU_POLISH_DONE"},
        ],
        "max_rows_over": lambda: [
            *_raw_collect_steps()[:2],
            {**_raw_collect_steps()[2], "maxRows": 11},
            *_raw_collect_steps()[3:],
        ],
        "screenshot_before_read": lambda: [
            _raw_collect_steps()[0],
            _raw_collect_steps()[1],
            _raw_collect_steps()[3],
            _raw_collect_steps()[2],
            _raw_collect_steps()[4],
        ],
    }
    for name, build in mutations.items():
        response = await _create_raw_task(client, device, build(), f"shape-bad-{name}")
        assert response.status_code == 422, f"{name}: {response.text}"


async def test_companion_push_after_collect_is_the_full_loop(api):
    """Collect run -> (device would execute) -> companion pushes rows back."""
    client, _app = api
    device, auth = await _setup_device(client, "orders-loop")
    run = await _collect(client, device, "loop-key", direction="SOLD", max_rows=2)
    assert run.status_code == 201, run.text
    pushed = await _push(
        client,
        auth,
        [
            _order("loop-1", occurred="2026-09-15T09:30:00+00:00"),
            _order("loop-2", occurred="3分钟前"),
        ],
    )
    assert pushed.status_code == 201, pushed.text
    assert pushed.json() == {"accepted": 2, "duplicates": 0}
