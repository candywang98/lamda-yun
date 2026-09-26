"""Durable order receipts: test the HTTP contract on SQLite and disposable PG."""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import UTC, datetime, timedelta

import pytest
from cloudctl_api.db import AccountDeviceBindingRow, MobileTaskRow, OrderRow
from cloudctl_api.order_delivery import OrderDeliveryReceiptRow
from sqlalchemy import func, select
from test_fleet_orders_pagination import OTHER_TENANT, _count_pages, _order, _screens, _setup_device
from test_p14_recipe_versions import api, isolated_postgres, pg_url  # noqa: F401
from test_platform_tasks import _enroll, bind, create_account, identity

PROTOCOL = "order-delivery/1"


async def _heartbeat(client, auth, *, enabled=True):
    response = await client.post(
        "/companion/v2/devices/heartbeat",
        headers=auth,
        json={
            "companionVersion": "order-test",
            "accessibilityEnabled": True,
            "runnerState": "IDLE",
            **({"orderDeliveryProtocol": PROTOCOL} if enabled else {}),
        },
    )
    assert response.status_code == 200, response.text


async def _setup(client, *, account=True, capability=True, name="durable"):
    device, auth = await _setup_device(client, name)
    account_id = await create_account(client, name) if account else None
    if account_id:
        await bind(client, account_id, device)
    await _heartbeat(client, auth, enabled=capability)
    return device, account_id, auth


async def _collect(client, device, *, key="durable", screens=3, **changes):
    return await client.post(
        "/api/v1/xianyu/orders:collect",
        headers={**identity(), "Idempotency-Key": key},
        json={
            "deviceId": device,
            "direction": "SOLD",
            "maxRows": 5,
            "screens": screens,
            "orderDeliveryProtocol": PROTOCOL,
            **changes,
        },
    )


async def _start(client, *, screens=3, name="durable"):
    device, account, auth = await _setup(client, name=name)
    response = await _collect(client, device, screens=screens, key=name)
    assert response.status_code == 201, response.text
    run = response.json()
    assert run["delivery"]["state"] == "PENDING"
    claim = await client.post(
        "/companion/v2/tasks/claim",
        headers=auth,
        json={"leaseSeconds": 60, "orderDeliveryProtocol": PROTOCOL},
    )
    assert claim.status_code == 200, claim.text
    task = claim.json()
    assert task["accountId"] == account
    assert task["bindingVersion"] == 1
    assert task["orderDelivery"]["maxScreens"] == screens
    assert task["orderDelivery"]["protocolVersion"] == PROTOCOL
    assert task["taskId"] == run["taskIds"][0]
    return device, account, auth, run, task


def _payload(task, account, *, screen=1, rows=None, **changes):
    return {
        "runKey": task["taskId"],
        "accountKey": account,
        "direction": "SOLD",
        "schemaVersion": 1,
        "screen": screen,
        "rows": [_order(f"order-{screen}")] if rows is None else rows,
        "partialRows": [],
        "collectedAt": "2026-09-26T12:00:00Z",
        **changes,
    }


def _envelope(task, payload, *, kind="SCREEN"):
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return {
        "protocolVersion": PROTOCOL,
        "taskId": task["taskId"],
        "kind": kind,
        "screen": payload["screen"] if kind == "SCREEN" else 0,
        "payloadJson": text,
        "payloadSha256": hashlib.sha256(text.encode()).hexdigest(),
    }


async def _push(client, auth, task, payload, *, kind="SCREEN"):
    return await client.post(
        "/companion/v2/orders/delivery",
        headers=auth,
        json=_envelope(task, payload, kind=kind),
    )


async def _complete(client, auth, task, account, *, count=1):
    return await _push(
        client,
        auth,
        task,
        {
            "runKey": task["taskId"],
            "accountKey": account,
            "direction": "SOLD",
            "totalScreens": count,
            "stopReason": "PLAN_FINISHED",
        },
        kind="COMPLETE",
    )


async def _view(client, run):
    result = await client.get(f"/api/v1/xianyu/orders/runs/{run['runId']}", headers=identity())
    assert result.status_code == 200, result.text
    return result.json()


async def _set_state(app, task, state):
    async with app.state.database.unit_of_work() as session:
        row = await session.get(MobileTaskRow, task["taskId"])
        row.business_state = state
        row.status = state
        row.lease_expires_at = datetime.now(UTC) - timedelta(hours=1)


async def test_atomic_identity_claim_negotiation_and_stale_capability(api):  # noqa: F811
    client, app = api
    device, account, auth = await _setup(client)
    created = await _collect(client, device)
    assert created.status_code == 201, created.text
    task_id = created.json()["taskIds"][0]
    async with app.state.database.unit_of_work() as session:
        row = await session.get(MobileTaskRow, task_id)
        assert row.batch_id == created.json()["runId"]
        assert row.account_id == account
        assert row.steps[0]["orderCollection"]["mobileBindingId"]
    old_claim = await client.post("/companion/v2/tasks/claim", headers=auth, json={})
    assert old_claim.status_code == 204
    await _heartbeat(client, auth, enabled=False)
    stale = await client.post(
        "/companion/v2/tasks/claim", headers=auth, json={"orderDeliveryProtocol": PROTOCOL}
    )
    assert stale.status_code == 204
    await _heartbeat(client, auth)
    claim = await client.post(
        "/companion/v2/tasks/claim", headers=auth, json={"orderDeliveryProtocol": PROTOCOL}
    )
    assert claim.status_code == 200, claim.text
    assert claim.json()["taskId"] == task_id


@pytest.mark.parametrize("account,capability", [(False, True), (True, False)])
async def test_gates_fail_before_creating_tasks(api, account, capability):  # noqa: F811
    client, app = api
    device, _, _ = await _setup(client, account=account, capability=capability)
    response = await _collect(client, device)
    assert response.status_code == 409
    async with app.state.database.unit_of_work() as session:
        assert await session.scalar(select(func.count()).select_from(MobileTaskRow)) == 0


async def test_accepted_replay_preserves_original_identity_after_unbind(api):  # noqa: F811
    client, app = api
    device, account, _ = await _setup(client)
    first = await _collect(client, device)
    assert first.status_code == 201
    async with app.state.database.unit_of_work() as session:
        bound = await session.scalar(
            select(AccountDeviceBindingRow).where(AccountDeviceBindingRow.account_id == account)
        )
        bound.status = "UNBOUND"
    replay = await _collect(client, device)
    assert replay.status_code == 200, replay.text
    assert replay.json()["taskIds"] == first.json()["taskIds"]
    assert replay.json()["delivery"]["stopReason"] == "ACCOUNT_BINDING_CHANGED"
    for change in ({"screens": 2}, {"direction": "BOUGHT"}, {"maxRows": 4}):
        conflict = await _collect(client, device, **change)
        assert conflict.status_code == 409


async def test_receipts_survive_expired_lease_and_terminal_collection(api):  # noqa: F811
    client, app = api
    _, account, auth, run, task = await _start(client, screens=1)
    await _set_state(app, task, "SUCCEEDED")
    before = await _view(client, run)
    assert before["allTerminal"] is True
    assert before["delivery"]["state"] == "PENDING"
    assert before["delivery"]["expectedScreens"] is None
    payload = _payload(task, account)
    first = await _push(client, auth, task, payload)
    assert first.status_code == 201, first.text
    assert first.json() == {
        **{k: v for k, v in _envelope(task, payload).items() if k != "payloadJson"},
        "accepted": True,
        "replayed": False,
    }
    replay = await _push(client, auth, task, payload)
    assert replay.status_code == 200
    assert replay.json()["replayed"] is True
    assert (await _view(client, run))["delivery"]["state"] == "PENDING"
    completion = await _complete(client, auth, task, account)
    assert completion.status_code == 201, completion.text
    assert (await _complete(client, auth, task, account)).status_code == 200
    result = (await _view(client, run))["delivery"]
    assert result == {
        "protocolVersion": PROTOCOL,
        "state": "SYNCED",
        "receivedScreens": [1],
        "expectedScreens": 1,
        "collectionComplete": True,
        "stopReason": "PLAN_FINISHED",
    }
    assert await _count_pages(app) == 1


async def test_completion_does_not_imply_execution_success_and_seals_run(api):  # noqa: F811
    client, _ = api
    _, account, auth, run, task = await _start(client)
    assert (await _complete(client, auth, task, account)).status_code == 409
    assert (await _push(client, auth, task, _payload(task, account, screen=2))).status_code == 409
    empty = _payload(task, account, rows=[])
    assert (await _push(client, auth, task, empty)).status_code == 201
    assert (await _complete(client, auth, task, account, count=2)).status_code == 409
    assert (await _complete(client, auth, task, account)).status_code == 201
    view = (await _view(client, run))["delivery"]
    assert view["state"] == "PENDING"
    assert view["collectionComplete"] is False
    assert view["receivedScreens"] == [1]
    assert (await _push(client, auth, task, _payload(task, account, screen=2))).status_code == 409


async def test_digest_conflict_is_persistent_and_original_page_is_unchanged(api):  # noqa: F811
    client, app = api
    _, account, auth, run, task = await _start(client)
    original = _payload(task, account)
    assert (await _push(client, auth, task, original)).status_code == 201
    changed = _payload(task, account, rows=[_order("replaced")])
    assert (await _push(client, auth, task, changed)).status_code == 409
    assert (await _push(client, auth, task, original)).status_code == 200
    assert (await _view(client, run))["delivery"]["stopReason"] == "PAYLOAD_CONFLICT"
    assert (await _complete(client, auth, task, account)).status_code == 409
    async with app.state.database.unit_of_work() as session:
        keys = list(await session.scalars(select(OrderRow.order_key)))
        assert keys == ["order-1"]
        assert await session.scalar(select(func.count()).select_from(OrderDeliveryReceiptRow)) == 1


async def test_malformed_changed_replay_still_records_conflict(api):  # noqa: F811
    client, app = api
    _, account, auth, run, task = await _start(client)
    envelope = _envelope(task, _payload(task, account))
    assert (
        await client.post("/companion/v2/orders/delivery", headers=auth, json=envelope)
    ).status_code == 201
    changed = {**envelope, "payloadJson": "{}", "payloadSha256": hashlib.sha256(b"{}").hexdigest()}
    response = await client.post("/companion/v2/orders/delivery", headers=auth, json=changed)
    assert response.status_code == 409
    await _set_state(app, task, "SUCCEEDED")
    assert (await _view(client, run))["delivery"]["stopReason"] == "PAYLOAD_CONFLICT"


@pytest.mark.parametrize(
    "state,reason",
    [
        ("FAILED", "TASK_FAILED"),
        ("CANCELLED", "TASK_CANCELLED"),
        ("EXPIRED", "TASK_EXPIRED"),
        ("RECONCILING", "COLLECTION_RECONCILING"),
    ],
)
async def test_failed_collection_can_deliver_retained_data_but_never_syncs(
    api,  # noqa: F811
    state,
    reason,
):
    client, app = api
    _, account, auth, run, task = await _start(client)
    await _set_state(app, task, state)
    assert (await _push(client, auth, task, _payload(task, account))).status_code == 201
    assert (await _complete(client, auth, task, account)).status_code == 201
    view = (await _view(client, run))["delivery"]
    assert view["state"] == "BLOCKED"
    assert view["stopReason"] == reason


async def test_scope_bounds_and_legacy_channel_are_rejected(api):  # noqa: F811
    client, app = api
    _, account, auth, run, task = await _start(client, screens=1)
    _, other_auth = await _setup_device(client, "other")
    payload = _payload(task, account)
    assert (await _push(client, other_auth, task, payload)).status_code == 404
    hidden = await client.get(f"/api/v1/xianyu/orders/runs/{run['runId']}", headers=OTHER_TENANT)
    assert hidden.status_code == 404
    for changed in (
        {"accountKey": "wrong"},
        {"runKey": "wrong"},
        {"direction": "BOUGHT"},
        {"screen": 2},
        {"schemaVersion": 2},
        {"rows": [_order("x", direction="BOUGHT")]},
    ):
        result = await _push(client, auth, task, {**payload, **changed})
        assert result.status_code in (409, 422), result.text
    legacy = await _screens(client, auth, run=task["taskId"], account=account, rows=[])
    assert legacy.status_code == 409
    assert await _count_pages(app) == 0


async def test_account_version_and_mobile_reenrollment_block_old_delivery(api):  # noqa: F811
    client, app = api
    device, account, auth, run, task = await _start(client)
    async with app.state.database.unit_of_work() as session:
        bound = await session.scalar(
            select(AccountDeviceBindingRow).where(AccountDeviceBindingRow.account_id == account)
        )
        bound.binding_version += 1
    assert (await _push(client, auth, task, _payload(task, account))).status_code == 409
    assert (await _view(client, run))["delivery"]["stopReason"] == "ACCOUNT_BINDING_CHANGED"
    new_auth = await _enroll(client, device, "replacement-instance")
    assert (await _push(client, new_auth, task, _payload(task, account))).status_code == 409
    assert (await _view(client, run))["delivery"]["stopReason"] == "MOBILE_BINDING_CHANGED"


async def test_not_started_and_invalid_envelopes_do_not_write(api):  # noqa: F811
    client, app = api
    device, account, auth = await _setup(client)
    created = await _collect(client, device)
    task = {"taskId": created.json()["taskIds"][0]}
    payload = _payload(task, account)
    assert (await _push(client, auth, task, payload)).status_code == 409
    envelope = _envelope(task, payload)
    invalid = await client.post(
        "/companion/v2/orders/delivery",
        headers=auth,
        json={**envelope, "payloadSha256": "0" * 64},
    )
    assert invalid.status_code == 422
    huge = "界" * 70_000
    invalid = await client.post(
        "/companion/v2/orders/delivery",
        headers=auth,
        json={
            **envelope,
            "payloadJson": huge,
            "payloadSha256": hashlib.sha256(huge.encode()).hexdigest(),
        },
    )
    assert invalid.status_code == 422
    assert await _count_pages(app) == 0


async def test_legacy_success_is_explicitly_unverified(api):  # noqa: F811
    client, app = api
    device, _, _ = await _setup(client)
    response = await _collect(client, device, orderDeliveryProtocol=None)
    assert response.status_code == 201
    run = response.json()
    await _set_state(app, {"taskId": run["taskIds"][0]}, "SUCCEEDED")
    delivery = (await _view(client, run))["delivery"]
    assert delivery["state"] == "LEGACY_UNVERIFIED"
    assert delivery["protocolVersion"] is None


async def test_postgres_concurrent_creation_and_receipt_replay(api):  # noqa: F811
    client, app = api
    if app.state.database.engine.dialect.name != "postgresql":
        pytest.skip("row-lock concurrency requires PostgreSQL")
    device, account, auth = await _setup(client)
    results = await asyncio.gather(*[_collect(client, device) for _ in range(5)])
    assert sorted(r.status_code for r in results) == [200, 200, 200, 200, 201]
    assert len({r.json()["taskIds"][0] for r in results}) == 1
    claim = await client.post(
        "/companion/v2/tasks/claim", headers=auth, json={"orderDeliveryProtocol": PROTOCOL}
    )
    assert claim.status_code == 200, claim.text
    task = claim.json()
    results = await asyncio.gather(
        *[_push(client, auth, task, _payload(task, account)) for _ in range(5)]
    )
    assert sorted(r.status_code for r in results) == [200, 200, 200, 200, 201]
    assert await _count_pages(app) == 1


async def test_runs_have_independent_contiguous_ordinals(api):  # noqa: F811
    client, app = api
    device, account, auth, _, first_task = await _start(client)
    assert (await _push(client, auth, first_task, _payload(first_task, account))).status_code == 201
    await _set_state(app, first_task, "SUCCEEDED")
    created = await _collect(client, device, key="second-run")
    assert created.status_code == 201
    claim = await client.post(
        "/companion/v2/tasks/claim", headers=auth, json={"orderDeliveryProtocol": PROTOCOL}
    )
    assert claim.status_code == 200, claim.text
    second = claim.json()
    assert second["taskId"] != first_task["taskId"]
    assert (
        await _push(client, auth, second, _payload(second, account, screen=2))
    ).status_code == 409
    assert (await _push(client, auth, second, _payload(second, account))).status_code == 201
    assert (
        await _push(client, auth, first_task, _payload(first_task, account, screen=2))
    ).status_code == 201
    assert (await _complete(client, auth, second, account)).status_code == 201
    assert (await _complete(client, auth, first_task, account, count=2)).status_code == 201
    assert await _count_pages(app) == 3


async def test_late_old_run_retains_receipts_without_reverting_newer_order(api):  # noqa: F811
    client, app = api
    device, account, auth, old_run, old = await _start(client, screens=1)
    await _set_state(app, old, "SUCCEEDED")
    created = await _collect(client, device, key="newer", screens=1)
    assert created.status_code == 201
    newer_run = created.json()
    claim = await client.post(
        "/companion/v2/tasks/claim", headers=auth, json={"orderDeliveryProtocol": PROTOCOL}
    )
    assert claim.status_code == 200
    newer = claim.json()
    await _set_state(app, newer, "SUCCEEDED")
    for task, status, observed in (
        (newer, "COMPLETED", "2026-09-26T12:00:00Z"),
        # An old outbox remains older even if the device clock was ahead.
        (old, "AWAITING_SHIPMENT", "2026-09-27T12:00:00Z"),
    ):
        result = await _push(
            client,
            auth,
            task,
            _payload(task, account, rows=[_order("shared", status=status)], collectedAt=observed),
        )
        assert result.status_code == 201, result.text
        assert (await _complete(client, auth, task, account)).status_code == 201
    async with app.state.database.unit_of_work() as session:
        row = await session.scalar(select(OrderRow).where(OrderRow.order_key == "shared"))
        assert row.status_text == "COMPLETED"
        assert await session.scalar(select(func.count()).select_from(OrderDeliveryReceiptRow)) == 4
    assert (await _view(client, old_run))["delivery"]["state"] == "SYNCED"
    assert (await _view(client, newer_run))["delivery"]["state"] == "SYNCED"
    assert await _count_pages(app) == 2


async def test_post_replay_uses_same_task_snapshot_as_delivery(api, monkeypatch):  # noqa: F811
    client, app = api
    device, account, auth, run, task = await _start(client, screens=1)
    assert (await _push(client, auth, task, _payload(task, account))).status_code == 201
    assert (await _complete(client, auth, task, account)).status_code == 201
    await _set_state(app, task, "SUCCEEDED")
    original = app.state.mobile_task_service._insert_task

    async def stale_insert_view(**kwargs):
        view, created = await original(**kwargs)
        return {**view, "status": "QUEUED", "businessState": "QUEUED"}, created

    monkeypatch.setattr(app.state.mobile_task_service, "_insert_task", stale_insert_view)
    replay = await _collect(client, device, screens=1)
    assert replay.status_code == 200, replay.text
    assert replay.json()["runId"] == run["runId"]
    assert replay.json()["tasks"][0]["state"] == "SUCCEEDED"
    assert replay.json()["delivery"]["state"] == "SYNCED"


async def test_order_upsert_failure_rolls_back_receipt_and_page(api, monkeypatch):  # noqa: F811
    client, app = api
    _, account, auth, _, task = await _start(client)
    service = app.state.order_delivery_service
    original = service.orders._upsert_orders

    async def fail_after_upsert(*args):
        await original(*args)
        raise RuntimeError("test transaction boundary")

    monkeypatch.setattr(service.orders, "_upsert_orders", fail_after_upsert)
    with pytest.raises(RuntimeError, match="test transaction boundary"):
        await _push(client, auth, task, _payload(task, account))
    async with app.state.database.unit_of_work() as session:
        assert await session.scalar(select(func.count()).select_from(OrderRow)) == 0
        assert await session.scalar(select(func.count()).select_from(OrderDeliveryReceiptRow)) == 0
    assert await _count_pages(app) == 0
    monkeypatch.setattr(service.orders, "_upsert_orders", original)
    assert (await _push(client, auth, task, _payload(task, account))).status_code == 201


async def test_three_devices_do_not_share_receipts_or_block_each_other(api):  # noqa: F811
    client, app = api
    phones = [await _start(client, name=f"phone-{i}") for i in range(3)]
    if app.state.database.engine.dialect.name == "postgresql":
        results = await asyncio.gather(
            *[
                _push(client, auth, task, _payload(task, account))
                for _, account, auth, _, task in phones
            ]
        )
    else:
        results = [
            await _push(client, auth, task, _payload(task, account))
            for _, account, auth, _, task in phones
        ]
    assert all(result.status_code == 201 for result in results)
    _, account, auth, run, task = phones[0]
    conflict = await _push(client, auth, task, _payload(task, account, rows=[]))
    assert conflict.status_code == 409
    assert (await _view(client, run))["delivery"]["state"] == "BLOCKED"
    for _, account, auth, run, task in phones[1:]:
        await _set_state(app, task, "SUCCEEDED")
        assert (await _complete(client, auth, task, account)).status_code == 201
        assert (await _view(client, run))["delivery"]["state"] == "SYNCED"
    assert await _count_pages(app) == 3


@pytest.mark.parametrize("status", ["REVOKED", "EXPIRED", "DISABLED"])
async def test_invalid_account_never_creates_durable_work(api, status):  # noqa: F811
    from cloudctl_api.db import PlatformAccountRow

    client, app = api
    device, account, _ = await _setup(client)
    async with app.state.database.unit_of_work() as session:
        row = await session.get(PlatformAccountRow, account)
        row.status = status
    result = await _collect(client, device)
    assert result.status_code == 409
    async with app.state.database.unit_of_work() as session:
        assert await session.scalar(select(func.count()).select_from(MobileTaskRow)) == 0
