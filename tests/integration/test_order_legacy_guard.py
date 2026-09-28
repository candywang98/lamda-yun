"""Regression coverage for legacy order pages after durable projection ownership."""

from __future__ import annotations

import asyncio

import pytest
from cloudctl_api.db import OrderRow
from cloudctl_api.fleet_orders import FleetOrderCheckpointRow, FleetOrderPageRow
from cloudctl_api.order_delivery import OrderDeliveryProjectionRow, OrderDeliveryReceiptRow
from sqlalchemy import func, select
from test_fleet_orders_pagination import OTHER_TENANT, _order, _screens, _setup_device
from test_order_delivery import PROTOCOL, _collect, _payload, _push, _set_state, _start
from test_p14_recipe_versions import api, isolated_postgres, pg_url  # noqa: F401


async def _count(session, model) -> int:
    return int(await session.scalar(select(func.count()).select_from(model)) or 0)


async def _checkpoint_snapshot(app):
    async with app.state.database.unit_of_work() as session:
        row = await session.scalar(select(FleetOrderCheckpointRow))
        return (
            row.account_key,
            row.schema_version,
            row.run_key,
            row.last_screen,
            row.seen_keys,
            row.updated_at,
        )


@pytest.mark.parametrize(
    "legacy_row",
    [
        pytest.param(_order("shared", status="AWAITING_SHIPMENT"), id="stale-status"),
        pytest.param({"direction": "SOLD", "order_key": "shared"}, id="missing-fields"),
    ],
)
async def test_protected_legacy_rows_are_rejected_without_mutation(  # noqa: F811
    api,  # noqa: F811
    legacy_row,
):
    client, app = api
    _, account, auth, _, task = await _start(client, screens=1, name="legacy-protected-stale")
    durable = await _push(
        client,
        auth,
        task,
        _payload(task, account, rows=[_order("shared", status="COMPLETED")]),
    )
    assert durable.status_code == 201, durable.text

    legacy = await _screens(
        client,
        auth,
        run="legacy-stale",
        account="legacy-account",
        rows=[legacy_row],
    )
    assert legacy.status_code == 409, legacy.text
    assert legacy.json()["detail"] == "ORDER_DELIVERY_PROTOCOL_REQUIRED"

    async with app.state.database.unit_of_work() as session:
        order = await session.scalar(select(OrderRow).where(OrderRow.order_key == "shared"))
        source = await session.get(OrderDeliveryProjectionRow, order.id)
        assert order.status_text == "COMPLETED"
        assert source.task_id == task["taskId"]
        assert source.screen == 1
        assert await _count(session, OrderRow) == 1
        assert await _count(session, FleetOrderPageRow) == 1
        assert await _count(session, FleetOrderCheckpointRow) == 0
        assert await _count(session, OrderDeliveryProjectionRow) == 1
        assert await _count(session, OrderDeliveryReceiptRow) == 1


async def test_mixed_protected_page_rolls_back_all_legacy_rows(api):  # noqa: F811
    client, app = api
    _, account, auth, _, task = await _start(client, screens=1, name="legacy-mixed")
    assert (
        await _push(
            client,
            auth,
            task,
            _payload(task, account, rows=[_order("protected", status="COMPLETED")]),
        )
    ).status_code == 201

    response = await _screens(
        client,
        auth,
        run="legacy-mixed-page",
        rows=[
            _order("legacy-new"),
            _order("protected", status="AWAITING_SHIPMENT"),
        ],
    )
    assert response.status_code == 409, response.text
    assert response.json()["detail"] == "ORDER_DELIVERY_PROTOCOL_REQUIRED"

    async with app.state.database.unit_of_work() as session:
        rows = {row.order_key: row for row in await session.scalars(select(OrderRow))}
        source = await session.get(OrderDeliveryProjectionRow, rows["protected"].id)
        assert set(rows) == {"protected"}
        assert rows["protected"].status_text == "COMPLETED"
        assert source.task_id == task["taskId"]
        assert source.screen == 1
        assert await _count(session, FleetOrderPageRow) == 1
        assert await _count(session, FleetOrderCheckpointRow) == 0
        assert await _count(session, OrderDeliveryProjectionRow) == 1
        assert await _count(session, OrderDeliveryReceiptRow) == 1


async def test_protected_new_page_precedes_checkpoint_conflicts(api):  # noqa: F811
    client, _ = api
    _, account, auth, _, task = await _start(client, screens=1, name="legacy-checkpoint-precedence")
    assert (
        await _push(
            client,
            auth,
            task,
            _payload(task, account, rows=[_order("protected", status="COMPLETED")]),
        )
    ).status_code == 201
    first = await _screens(
        client,
        auth,
        run="legacy-checkpoint-run",
        rows=[_order("legacy-only")],
    )
    assert first.status_code == 201, first.text

    protected = await _screens(
        client,
        auth,
        run="legacy-checkpoint-run",
        version=2,
        screen=3,
        rows=[_order("protected", status="AWAITING_SHIPMENT")],
    )
    assert protected.status_code == 409, protected.text
    assert protected.json()["detail"] == "ORDER_DELIVERY_PROTOCOL_REQUIRED"


async def test_accepted_legacy_page_replay_stays_read_only_after_projection(api):  # noqa: F811
    client, app = api
    _, account, auth, _, task = await _start(client, screens=1, name="legacy-replay")
    legacy_payload = [_order("shared", status="AWAITING_SHIPMENT")]
    first = await _screens(
        client,
        auth,
        run="accepted-legacy-page",
        account="legacy-account",
        rows=legacy_payload,
    )
    assert first.status_code == 201, first.text
    durable = await _push(
        client,
        auth,
        task,
        _payload(task, account, rows=[_order("shared", status="COMPLETED")]),
    )
    assert durable.status_code == 201, durable.text
    checkpoint_before = await _checkpoint_snapshot(app)

    replay = await _screens(
        client,
        auth,
        run="accepted-legacy-page",
        account="legacy-account",
        rows=legacy_payload,
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["replayed"] is True
    assert await _checkpoint_snapshot(app) == checkpoint_before

    async with app.state.database.unit_of_work() as session:
        order = await session.scalar(select(OrderRow).where(OrderRow.order_key == "shared"))
        source = await session.get(OrderDeliveryProjectionRow, order.id)
        assert order.status_text == "COMPLETED"
        assert source.task_id == task["taskId"]
        assert source.screen == 1
        assert await _count(session, OrderRow) == 1
        assert await _count(session, FleetOrderPageRow) == 2
        assert await _count(session, FleetOrderCheckpointRow) == 1
        assert await _count(session, OrderDeliveryProjectionRow) == 1
        assert await _count(session, OrderDeliveryReceiptRow) == 1


async def _setup_other_tenant_device(client):
    created = await client.post(
        "/api/v1/mobile/devices",
        headers=OTHER_TENANT,
        json={
            "logicalName": "legacy-other-tenant",
            "androidVersion": "14",
            "companionVersion": "1.0.0",
        },
    )
    assert created.status_code == 201, created.text
    device_id = created.json()["id"]
    enrollment = await client.post(
        "/api/v1/mobile/enrollments",
        headers=OTHER_TENANT,
        json={"deviceId": device_id, "ttlSeconds": 600},
    )
    assert enrollment.status_code == 201, enrollment.text
    token = await client.post(
        "/companion/v2/enroll",
        json={
            "code": enrollment.json()["code"],
            "appInstanceId": "legacy-other-tenant-instance",
            "companionVersion": "1.0.0",
        },
    )
    assert token.status_code == 201, token.text
    return {"Authorization": f"Bearer {token.json()['bindingToken']}"}


async def test_equal_key_other_device_and_tenant_remains_compatible(api):  # noqa: F811
    client, app = api
    _, account, auth, _, task = await _start(client, screens=1, name="legacy-scope")
    assert (
        await _push(
            client,
            auth,
            task,
            _payload(task, account, rows=[_order("shared", status="COMPLETED")]),
        )
    ).status_code == 201

    _, other_device_auth = await _setup_device(client, "legacy-other-device")
    other_device = await _screens(
        client,
        other_device_auth,
        run="other-device-run",
        rows=[_order("shared", status="AWAITING_SHIPMENT")],
    )
    assert other_device.status_code == 201, other_device.text

    other_tenant_auth = await _setup_other_tenant_device(client)
    other_tenant = await _screens(
        client,
        other_tenant_auth,
        run="other-tenant-run",
        rows=[_order("shared", status="AWAITING_SHIPMENT")],
    )
    assert other_tenant.status_code == 201, other_tenant.text

    async with app.state.database.unit_of_work() as session:
        assert await _count(session, OrderRow) == 3
        assert await _count(session, OrderDeliveryProjectionRow) == 1


async def test_unprotected_legacy_pages_keep_status_update_compatibility(api):  # noqa: F811
    client, app = api
    _, auth = await _setup_device(client, "normal-legacy")
    first = await _screens(
        client,
        auth,
        run="normal-legacy-run",
        rows=[_order("legacy-only", status="AWAITING_SHIPMENT")],
    )
    assert first.status_code == 201, first.text
    second = await _screens(
        client,
        auth,
        run="normal-legacy-run",
        screen=2,
        rows=[
            _order("legacy-only", status="COMPLETED"),
            _order("legacy-second", status="COMPLETED"),
        ],
    )
    assert second.status_code == 201, second.text
    assert second.json()["accepted"] == 1
    assert second.json()["updated"] == 1

    async with app.state.database.unit_of_work() as session:
        rows = {row.order_key: row for row in await session.scalars(select(OrderRow))}
        assert rows["legacy-only"].status_text == "COMPLETED"
        assert set(rows) == {"legacy-only", "legacy-second"}
        assert await _count(session, OrderDeliveryProjectionRow) == 0


async def test_durable_generation_ordering_remains_authoritative(api):  # noqa: F811
    client, app = api
    device, account, auth, _, old = await _start(client, screens=1, name="generation-guard")
    await _set_state(app, old, "SUCCEEDED")
    created = await _collect(client, device, key="generation-newer", screens=1)
    assert created.status_code == 201, created.text
    claimed = await client.post(
        "/companion/v2/tasks/claim",
        headers=auth,
        json={"leaseSeconds": 60, "orderDeliveryProtocol": PROTOCOL},
    )
    assert claimed.status_code == 200, claimed.text
    newer = claimed.json()
    await _set_state(app, newer, "SUCCEEDED")

    assert (
        await _push(
            client,
            auth,
            newer,
            _payload(newer, account, rows=[_order("shared", status="COMPLETED")]),
        )
    ).status_code == 201
    stale = await _push(
        client,
        auth,
        old,
        _payload(old, account, rows=[_order("shared", status="AWAITING_SHIPMENT")]),
    )
    assert stale.status_code == 201, stale.text

    async with app.state.database.unit_of_work() as session:
        order = await session.scalar(select(OrderRow).where(OrderRow.order_key == "shared"))
        source = await session.get(OrderDeliveryProjectionRow, order.id)
        assert order.status_text == "COMPLETED"
        assert source.task_id == newer["taskId"]


async def test_postgres_durable_admission_serializes_legacy_guard(  # noqa: F811
    api,  # noqa: F811
    monkeypatch,
):
    client, app = api
    if app.state.database.engine.dialect.name != "postgresql":
        pytest.skip("row-lock serialization requires PostgreSQL")
    _, account, auth, _, task = await _start(client, screens=1, name="legacy-lock")
    entered = asyncio.Event()
    release = asyncio.Event()
    service = app.state.order_delivery_service
    original = service._upsert_observed_orders

    async def pause_after_device_lock(*args):
        entered.set()
        await release.wait()
        return await original(*args)

    monkeypatch.setattr(service, "_upsert_observed_orders", pause_after_device_lock)
    durable_task = asyncio.create_task(
        _push(
            client,
            auth,
            task,
            _payload(task, account, rows=[_order("shared", status="COMPLETED")]),
        )
    )
    await asyncio.wait_for(entered.wait(), timeout=2)
    legacy_task = asyncio.create_task(
        _screens(
            client,
            auth,
            run="legacy-lock-race",
            rows=[_order("shared", status="AWAITING_SHIPMENT")],
        )
    )
    await asyncio.sleep(0.1)
    assert not legacy_task.done()
    release.set()
    durable, legacy = await asyncio.gather(durable_task, legacy_task)
    assert durable.status_code == 201, durable.text
    assert legacy.status_code == 409, legacy.text
    assert legacy.json()["detail"] == "ORDER_DELIVERY_PROTOCOL_REQUIRED"


async def test_postgres_legacy_admission_can_precede_durable_projection(  # noqa: F811
    api,  # noqa: F811
    monkeypatch,
):
    client, app = api
    if app.state.database.engine.dialect.name != "postgresql":
        pytest.skip("row-lock serialization requires PostgreSQL")
    _, account, auth, _, task = await _start(client, screens=1, name="legacy-lock-first")
    entered = asyncio.Event()
    release = asyncio.Event()
    service = app.state.fleet_orders_service
    original = service._has_delivery_projection

    async def pause_after_device_lock(*args):
        entered.set()
        await release.wait()
        return await original(*args)

    monkeypatch.setattr(service, "_has_delivery_projection", pause_after_device_lock)
    legacy_task = asyncio.create_task(
        _screens(
            client,
            auth,
            run="legacy-lock-first-run",
            rows=[_order("shared", status="AWAITING_SHIPMENT")],
        )
    )
    await asyncio.wait_for(entered.wait(), timeout=2)
    durable_task = asyncio.create_task(
        _push(
            client,
            auth,
            task,
            _payload(task, account, rows=[_order("shared", status="COMPLETED")]),
        )
    )
    await asyncio.sleep(0.1)
    assert not durable_task.done()
    release.set()
    legacy, durable = await asyncio.gather(legacy_task, durable_task)
    assert legacy.status_code == 201, legacy.text
    assert durable.status_code == 201, durable.text

    async with app.state.database.unit_of_work() as session:
        order = await session.scalar(select(OrderRow).where(OrderRow.order_key == "shared"))
        source = await session.get(OrderDeliveryProjectionRow, order.id)
        assert order.status_text == "COMPLETED"
        assert source.task_id == task["taskId"]
