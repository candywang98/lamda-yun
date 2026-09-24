"""IM aggregation slice 1 (pa-im/20260913.1): ingest, inbox, gated reply."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from test_control_api_migrations import migration_config
from test_p14_recipe_versions import (  # noqa: F401 - pytest fixture injection
    api,
    isolated_postgres,
    pg_url,
)
from test_platform_tasks import _enroll, create_direct_device, identity

PLATFORM = "xianyu"


def _message(peer: str, text: str, when: datetime, name: str | None = None):
    return {
        "platform": PLATFORM,
        "peerKey": peer,
        "peerName": name or peer,
        "text": text,
        "occurredAt": when.isoformat(),
    }


async def _push(client, auth, peer="buyer_a", text="你好，还在吗？", when=None):
    when = when or datetime.now(UTC)
    response = await client.post(
        "/companion/v2/im/messages",
        headers=auth,
        json={"messages": [_message(peer, text, when)]},
    )
    assert response.status_code == 200, response.text
    return response.json()


async def test_ingest_is_idempotent_and_merges_threads(api):  # noqa: F811
    client, _app = api
    device = await create_direct_device(client, "im-dev")
    auth = await _enroll(client, device, "im-instance")
    when = datetime.now(UTC).replace(microsecond=0)

    first = await _push(client, auth, when=when)
    assert first == {"accepted": 1, "duplicates": 0}
    repeat = await _push(client, auth, when=when)
    assert repeat == {"accepted": 0, "duplicates": 1}

    later = when + timedelta(seconds=5)
    await _push(client, auth, text="第二条", when=later)
    threads = (await client.get("/api/v1/im/threads", headers=identity())).json()["items"]
    assert len(threads) == 1
    thread = threads[0]
    assert thread["peerName"] == "buyer_a"
    assert thread["unreadCount"] == 2
    assert thread["lastDirection"] == "IN"
    assert thread["lastMessageText"] == "第二条"

    messages = (
        await client.get(f"/api/v1/im/threads/{thread['id']}/messages", headers=identity())
    ).json()["items"]
    assert [m["text"] for m in messages] == ["你好，还在吗？", "第二条"]

    marked = await client.post(f"/api/v1/im/threads/{thread['id']}:mark-read", headers=identity())
    assert marked.status_code == 200
    assert marked.json()["unreadCount"] == 0


async def test_ingest_requires_supported_platform(api):  # noqa: F811
    client, _app = api
    device = await create_direct_device(client, "im-platform-dev")
    auth = await _enroll(client, device, "im-platform-instance")
    when = datetime.now(UTC).replace(microsecond=0)
    base = _message("buyer_platform", "仅收闲鱼", when)

    missing = dict(base)
    missing.pop("platform")
    missing_response = await client.post(
        "/companion/v2/im/messages", headers=auth, json={"messages": [missing]}
    )
    assert missing_response.status_code == 422

    unsupported = {**base, "platform": "xhs"}
    unsupported_response = await client.post(
        "/companion/v2/im/messages", headers=auth, json={"messages": [unsupported]}
    )
    assert unsupported_response.status_code == 422

    assert await _push(client, auth, peer="buyer_platform", text="仅收闲鱼", when=when) == {
        "accepted": 1,
        "duplicates": 0,
    }


def test_hashes_match_shared_android_fixtures():
    from cloudctl_api.im_service import _dedupe_key, canonical_text

    fixture = json.loads(
        (
            Path(__file__).resolve().parents[2] / "contracts/fixtures/im-m3-canonical.json"
        ).read_text()
    )
    occurred = datetime.fromtimestamp(fixture["epochSecond"], UTC)
    for sample in fixture["cases"]:
        raw = sample["character"] * sample["repeat"] + sample["suffix"]
        for text in (raw, canonical_text(raw)):
            assert (
                _dedupe_key(
                    fixture["deviceId"], fixture["platform"], fixture["peerKey"], occurred, text
                )
                == sample["sha256"]
            ), sample["name"]


async def test_canonical_text_and_cross_device_dedupe_fixture(api):  # noqa: F811
    from cloudctl_api.db import ImMessageRow
    from cloudctl_api.im_service import _dedupe_key, canonical_text
    from sqlalchemy import select

    client, app = api
    device = await create_direct_device(client, "im-canonical-dev")
    auth = await _enroll(client, device, "im-canonical-instance")
    when = datetime.fromtimestamp(1_800_000_000, UTC)
    emoji = "😀"
    fixtures = [
        ("a" * 2000, "a" * 2000),
        ("b" * 2001, "TRUNCATED " + "b" * 2000),
        ("c" * 4500, "TRUNCATED " + "c" * 2000),
        ("d" * 1999 + emoji + "z", "TRUNCATED " + "d" * 1999 + emoji),
    ]
    for raw, expected in fixtures:
        assert canonical_text(raw) == expected
        assert canonical_text(expected) == expected

    canonical = fixtures[-1][1]
    expected_hash = hashlib.sha256(
        f"{device}|xianyu|买家|1800000000|{canonical}".encode()
    ).hexdigest()
    assert _dedupe_key(device, "xianyu", "买家", when, fixtures[-1][0]) == expected_hash
    assert _dedupe_key(device, "xianyu", "买家", when, canonical) == expected_hash
    assert "b0644fb5" not in expected_hash

    first = await _push(client, auth, peer="买家", text=fixtures[-1][0], when=when)
    replay = await _push(client, auth, peer="买家", text=canonical, when=when)
    assert first == {"accepted": 1, "duplicates": 0}
    assert replay == {"accepted": 0, "duplicates": 1}
    async with app.state.database.unit_of_work() as session:
        rows = list(await session.scalars(select(ImMessageRow)))
        assert len(rows) == 1
        assert rows[0].text_content == canonical
        assert rows[0].dedupe_key == expected_hash


async def test_reply_creates_claimable_task_and_rate_limits(api):  # noqa: F811
    client, app = api
    device = await create_direct_device(client, "im-reply-dev")
    auth = await _enroll(client, device, "im-reply-instance")
    when = datetime.now(UTC).replace(microsecond=0)
    await _push(client, auth, peer="buyer_b", text="能便宜点吗", when=when)
    thread = (await client.get("/api/v1/im/threads", headers=identity())).json()["items"][0]

    reply = await client.post(
        f"/api/v1/im/threads/{thread['id']}:reply", headers=identity(), json={"text": "一口价199"}
    )
    assert reply.status_code == 201, reply.text
    task_id = reply.json()["taskId"]

    from cloudctl_api.db import MobileTaskRow

    async with app.state.database.unit_of_work() as session:
        row = await session.get(MobileTaskRow, task_id)
        assert row is not None and row.target_package == "com.taobao.idlefish"
        real_steps = [step for step in row.steps if step.get("action")]
        actions = [step["action"] for step in real_steps]
        assert actions == [
            "ui.find",
            "ui.tap",
            "ui.tapText",
            "ui.wait",
            "ui.input",
            "ui.tap",
        ]
        tap_text = next(step for step in real_steps if step["action"] == "ui.tapText")
        assert tap_text["value"] == "buyer_b"

    # The reply task must be claimable by the bound companion.
    from test_p14_recipe_versions import claim

    claimed = await claim(client, auth)
    assert claimed["taskId"] == task_id

    # Second reply within the cooldown is rejected even after the task finished.
    await client.post(
        f"/companion/v2/tasks/{task_id}/heartbeat",
        headers=auth,
        json={"leaseId": claimed["leaseId"], "currentStep": 0},
    )
    rate = await client.post(
        f"/api/v1/im/threads/{thread['id']}:reply", headers=identity(), json={"text": "再问一次"}
    )
    assert rate.status_code == 409
    assert "THREAD_REPLY_RATE_LIMITED" in rate.text


async def test_reply_rejects_busy_device_and_invalid_schema(api):  # noqa: F811
    client, app = api
    device = await create_direct_device(client, "im-busy-dev")
    auth = await _enroll(client, device, "im-busy-instance")
    when = datetime.now(UTC).replace(microsecond=0)
    await _push(client, auth, peer="buyer_c", text="发货了吗", when=when)
    thread = (await client.get("/api/v1/im/threads", headers=identity())).json()["items"][0]

    # Mark the device busy: a real claimed task in RUNNING state.
    created = await client.post(
        "/api/v1/mobile/tasks",
        headers={**identity(), "Idempotency-Key": f"im-busy-{device[:20]}"},
        json={
            "deviceId": device,
            "targetPackage": "com.taobao.idlefish",
            "totalTimeoutMs": 60_000,
            "steps": [
                {
                    "stepId": "idle",
                    "timeoutMs": 8000,
                    "action": "ui.wait",
                    "locatorRef": "xianyu_home_sell",
                    "condition": "EXISTS",
                    "pollMs": 200,
                },
            ],
        },
    )
    assert created.status_code == 201, created.text
    from test_p14_recipe_versions import claim

    claimed_busy = await claim(client, auth)
    assert claimed_busy["taskId"] == created.json()["taskId"]
    started = await client.post(
        f"/companion/v2/tasks/{claimed_busy['taskId']}/heartbeat",
        headers=auth,
        json={"leaseId": claimed_busy["leaseId"], "currentStep": 0},
    )
    assert started.status_code == 200, started.text
    busy = await client.post(
        f"/api/v1/im/threads/{thread['id']}:reply", headers=identity(), json={"text": "已发货"}
    )
    assert busy.status_code == 409
    assert "DEVICE_BUSY" in busy.text

    # Schema guards for ui.tapText.
    bad_task = await client.post(
        "/api/v1/mobile/tasks",
        headers={**identity(), "Idempotency-Key": "im-schema-1"},
        json={
            "deviceId": device,
            "targetPackage": "com.taobao.idlefish",
            "totalTimeoutMs": 60_000,
            "steps": [
                {"stepId": "open", "timeoutMs": 8000, "action": "ui.tapText", "value": ""},
            ],
        },
    )
    assert bad_task.status_code == 422
    long_value = await client.post(
        "/api/v1/mobile/tasks",
        headers={**identity(), "Idempotency-Key": "im-schema-2"},
        json={
            "deviceId": device,
            "targetPackage": "com.taobao.idlefish",
            "totalTimeoutMs": 60_000,
            "steps": [
                {"stepId": "open", "timeoutMs": 8000, "action": "ui.tapText", "value": "x" * 65},
            ],
        },
    )
    assert long_value.status_code == 422


async def test_monitor_config_crud_and_companion_fetch(api):  # noqa: F811
    client, _app = api
    device = await create_direct_device(client, "im-cfg-dev")
    auth = await _enroll(client, device, "im-cfg-instance")

    default = await client.get("/api/v1/im/config", params={"deviceId": device}, headers=identity())
    assert default.status_code == 200
    assert default.json()["platforms"] == ["xianyu"]
    assert default.json()["mode"] == "NOTIFICATION"

    saved = await client.put(
        "/api/v1/im/config",
        params={"deviceId": device},
        headers=identity(),
        json={
            "enabled": True,
            "platforms": ["xianyu", "xhs", "douyin"],
            "mode": "DUTY",
            "dutyStart": "08:30",
            "dutyEnd": "22:00",
        },
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["platforms"] == ["xianyu", "xhs", "douyin"]
    assert saved.json()["mode"] == "DUTY"

    companion = await client.get("/companion/v2/im/config", headers=auth)
    assert companion.status_code == 200
    assert set(companion.json()["platforms"]) == {"xianyu", "xhs", "douyin"}
    assert companion.json()["dutyStart"] == "08:30"

    bad_platform = await client.put(
        "/api/v1/im/config",
        params={"deviceId": device},
        headers=identity(),
        json={"platforms": ["taobao"]},
    )
    assert bad_platform.status_code in (409, 422)


async def _thread_messages(client, thread_id):
    return (
        await client.get(f"/api/v1/im/threads/{thread_id}/messages", headers=identity())
    ).json()["items"]


def _out_message(items):
    return next(item for item in items if item["direction"] == "OUT")


async def test_reply_out_message_is_pending_until_task_fails(api):  # noqa: F811
    client, app = api
    device = await create_direct_device(client, "im-fail-dev")
    auth = await _enroll(client, device, "im-fail-instance")
    when = datetime.now(UTC).replace(microsecond=0)
    await _push(client, auth, peer="buyer_d", text="在吗", when=when)
    thread = (await client.get("/api/v1/im/threads", headers=identity())).json()["items"][0]

    reply = await client.post(
        f"/api/v1/im/threads/{thread['id']}:reply",
        headers=identity(),
        json={"text": "在的，可以直接拍下"},
    )
    assert reply.status_code == 201, reply.text
    task_id = reply.json()["taskId"]

    items = await _thread_messages(client, thread["id"])
    inbound = next(item for item in items if item["direction"] == "IN")
    assert inbound["deliveryState"] == "DELIVERED"
    out = _out_message(items)
    assert out["deliveryState"] == "PENDING"
    assert out["replyTaskId"] == task_id

    from test_p14_recipe_versions import claim

    claimed = await claim(client, auth)
    assert claimed["taskId"] == task_id
    failure = {
        "leaseId": claimed["leaseId"],
        "errorCode": "INPUT_IME_REQUIRED",
        "detail": "chat input rejected the replacement text",
    }
    failed = await client.post(f"/companion/v2/tasks/{task_id}/fail", headers=auth, json=failure)
    assert failed.status_code == 200, failed.text

    items = await _thread_messages(client, thread["id"])
    assert _out_message(items)["deliveryState"] == "FAILED"

    # A duplicated terminal failure report must not change the settled state.
    replay = await client.post(f"/companion/v2/tasks/{task_id}/fail", headers=auth, json=failure)
    assert replay.status_code == 200
    items = await _thread_messages(client, thread["id"])
    assert _out_message(items)["deliveryState"] == "FAILED"

    from cloudctl_api.db import ImMessageRow, MobileTaskRow
    from sqlalchemy import select

    async with app.state.database.unit_of_work() as session:
        task = await session.get(MobileTaskRow, task_id)
        assert (task.status, task.business_state) == ("FAILED", "FAILED")
        row = await session.scalar(
            select(ImMessageRow).where(ImMessageRow.reply_task_id == task_id)
        )
        assert row.delivery_state == "FAILED"


async def test_reply_delivery_succeeded_is_absorbing(api):  # noqa: F811
    client, app = api
    device = await create_direct_device(client, "im-ok-dev")
    auth = await _enroll(client, device, "im-ok-instance")
    when = datetime.now(UTC).replace(microsecond=0)
    await _push(client, auth, peer="buyer_e", text="能发货吗", when=when)
    thread = (await client.get("/api/v1/im/threads", headers=identity())).json()["items"][0]
    reply = await client.post(
        f"/api/v1/im/threads/{thread['id']}:reply", headers=identity(), json={"text": "今天发"}
    )
    assert reply.status_code == 201, reply.text
    task_id = reply.json()["taskId"]

    from test_p14_recipe_versions import claim

    claimed = await claim(client, auth)
    done = await client.post(
        f"/companion/v2/tasks/{task_id}/complete",
        headers=auth,
        json={"leaseId": claimed["leaseId"], "result": {}},
    )
    assert done.status_code == 200, done.text
    items = await _thread_messages(client, thread["id"])
    assert _out_message(items)["deliveryState"] == "DELIVERED"

    # A late failure report for a succeeded task is rejected by the terminal guard.
    late = await client.post(
        f"/companion/v2/tasks/{task_id}/fail",
        headers=auth,
        json={"leaseId": claimed["leaseId"], "errorCode": "STEP_TIMEOUT", "detail": "late report"},
    )
    assert late.status_code == 409
    items = await _thread_messages(client, thread["id"])
    assert _out_message(items)["deliveryState"] == "DELIVERED"

    # Defense in depth: even a direct settle call cannot downgrade DELIVERED,
    # and repeated settles of the same terminal state are no-ops.
    from cloudctl_api.db import ImMessageRow
    from cloudctl_api.im_service import settle_reply_delivery
    from sqlalchemy import select

    async with app.state.database.unit_of_work() as session:
        row = await session.scalar(
            select(ImMessageRow).where(ImMessageRow.reply_task_id == task_id)
        )
        assert row.delivery_state == "DELIVERED"
        await settle_reply_delivery(session, task_id, "FAILED")
        await settle_reply_delivery(session, task_id, "CANCELLED")
        await session.flush()
        await session.refresh(row)
        assert row.delivery_state == "DELIVERED"
        await settle_reply_delivery(session, task_id, "SUCCEEDED")
        await session.flush()
        await session.refresh(row)
        assert row.delivery_state == "DELIVERED"


async def test_cancelled_reply_task_marks_out_message_failed(api):  # noqa: F811
    client, _app = api
    device = await create_direct_device(client, "im-cancel-dev")
    auth = await _enroll(client, device, "im-cancel-instance")
    when = datetime.now(UTC).replace(microsecond=0)
    await _push(client, auth, peer="buyer_f", text="还在吗", when=when)
    thread = (await client.get("/api/v1/im/threads", headers=identity())).json()["items"][0]
    reply = await client.post(
        f"/api/v1/im/threads/{thread['id']}:reply", headers=identity(), json={"text": "在的"}
    )
    assert reply.status_code == 201, reply.text
    task_id = reply.json()["taskId"]

    cancelled = await client.post(
        f"/api/v1/platform-tasks/{task_id}:cancel",
        headers=identity(),
        json={"reason": "operator retracted the queued reply"},
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["state"] == "CANCELLED"

    items = await _thread_messages(client, thread["id"])
    assert _out_message(items)["deliveryState"] == "FAILED"


async def test_reconciled_reply_task_settles_delivery_state(api):  # noqa: F811
    client, _app = api
    device = await create_direct_device(client, "im-reconcile-dev")
    auth = await _enroll(client, device, "im-reconcile-instance")
    when = datetime.now(UTC).replace(microsecond=0)
    await _push(client, auth, peer="buyer_g", text="改价了吗", when=when)
    await _push(client, auth, peer="buyer_h", text="今天能发吗", when=when)
    threads = (await client.get("/api/v1/im/threads", headers=identity())).json()["items"]
    by_peer = {thread["peerKey"]: thread for thread in threads}

    from test_p14_recipe_versions import claim

    # Applied reconciliation confirms delivery.
    applied_thread = by_peer["buyer_g"]
    reply = await client.post(
        f"/api/v1/im/threads/{applied_thread['id']}:reply",
        headers=identity(),
        json={"text": "已改好"},
    )
    assert reply.status_code == 201, reply.text
    applied_task = reply.json()["taskId"]
    assert (await claim(client, auth))["taskId"] == applied_task
    unknown = await client.post(
        f"/api/v1/platform-tasks/{applied_task}:mark-unknown",
        headers=identity(),
        json={"reason": "runner lost connectivity mid-send"},
    )
    assert unknown.status_code == 200, unknown.text
    reconciled = await client.post(
        f"/api/v1/platform-tasks/{applied_task}:reconcile",
        headers=identity(),
        json={
            "decision": "CONFIRMED_APPLIED",
            "evidence": "operator verified the reply visible in the chat",
            "platformItemId": "chat-message-verified",
        },
    )
    assert reconciled.status_code == 200, reconciled.text
    assert reconciled.json()["state"] == "SUCCEEDED"
    items = await _thread_messages(client, applied_thread["id"])
    assert _out_message(items)["deliveryState"] == "DELIVERED"

    # Not-submitted reconciliation marks the reply as failed delivery.
    dropped_thread = by_peer["buyer_h"]
    reply = await client.post(
        f"/api/v1/im/threads/{dropped_thread['id']}:reply",
        headers=identity(),
        json={"text": "下午发"},
    )
    assert reply.status_code == 201, reply.text
    dropped_task = reply.json()["taskId"]
    assert (await claim(client, auth))["taskId"] == dropped_task
    unknown = await client.post(
        f"/api/v1/platform-tasks/{dropped_task}:mark-unknown",
        headers=identity(),
        json={"reason": "runner lost connectivity mid-send"},
    )
    assert unknown.status_code == 200, unknown.text
    reconciled = await client.post(
        f"/api/v1/platform-tasks/{dropped_task}:reconcile",
        headers=identity(),
        json={
            "decision": "CONFIRMED_NOT_SUBMITTED",
            "evidence": "operator confirmed the chat has no outgoing message",
        },
    )
    assert reconciled.status_code == 200, reconciled.text
    assert reconciled.json()["state"] == "FAILED"
    items = await _thread_messages(client, dropped_thread["id"])
    assert _out_message(items)["deliveryState"] == "FAILED"


async def test_threads_are_isolated_by_device_and_tenant_with_stable_pagination(api):  # noqa: F811
    client, _app = api
    device_a = await create_direct_device(client, "im-isolation-a")
    auth_a = await _enroll(client, device_a, "im-isolation-a-instance")
    device_b = await create_direct_device(client, "im-isolation-b")
    auth_b = await _enroll(client, device_b, "im-isolation-b-instance")
    when = datetime.now(UTC).replace(microsecond=0)

    await _push(client, auth_a, peer="same-peer", text="设备 A", when=when)
    await _push(client, auth_b, peer="same-peer", text="设备 B", when=when)
    all_threads = (
        await client.get("/api/v1/im/threads", headers=identity(), params={"limit": 1})
    ).json()["items"]
    assert len(all_threads) == 1
    page_two = (
        await client.get(
            "/api/v1/im/threads",
            headers=identity(),
            params={"limit": 1, "after": all_threads[0]["id"]},
        )
    ).json()["items"]
    assert len(page_two) == 1
    assert {all_threads[0]["deviceId"], page_two[0]["deviceId"]} == {device_a, device_b}
    assert {all_threads[0]["lastMessageText"], page_two[0]["lastMessageText"]} == {
        "设备 A",
        "设备 B",
    }

    only_a = (
        await client.get("/api/v1/im/threads", headers=identity(), params={"deviceId": device_a})
    ).json()["items"]
    assert [thread["deviceId"] for thread in only_a] == [device_a]

    other_tenant = {**identity(), "X-Tenant-Id": "00000000-0000-7000-8000-000000009999"}
    assert (await client.get("/api/v1/im/threads", headers=other_tenant)).json()["items"] == []
    hidden = await client.get(
        f"/api/v1/im/threads/{only_a[0]['id']}/messages", headers=other_tenant
    )
    assert hidden.status_code == 404


async def test_latest_messages_and_out_of_order_push_do_not_hide_new_text(api):  # noqa: F811
    client, _app = api
    device = await create_direct_device(client, "im-latest")
    auth = await _enroll(client, device, "im-latest-instance")
    when = datetime.now(UTC).replace(microsecond=0)
    await _push(client, auth, text="最新", when=when + timedelta(seconds=30))
    await _push(client, auth, text="补传旧消息", when=when)
    await _push(client, auth, text="中间消息", when=when + timedelta(seconds=10))
    thread = (await client.get("/api/v1/im/threads", headers=identity())).json()["items"][0]
    assert thread["lastMessageText"] == "最新"
    assert datetime.fromisoformat(
        thread["lastMessageAt"].replace("Z", "+00:00")
    ) == when + timedelta(seconds=30)
    url = f"/api/v1/im/threads/{thread['id']}/messages"
    latest = (
        await client.get(url, headers=identity(), params={"latest": True, "limit": 2})
    ).json()["items"]
    assert [item["text"] for item in latest] == ["中间消息", "最新"]
    oldest = (await client.get(url, headers=identity(), params={"limit": 1})).json()["items"]
    rest = (await client.get(url, headers=identity(), params={"after": oldest[0]["id"]})).json()[
        "items"
    ]
    assert [item["text"] for item in rest] == ["中间消息", "最新"]
    assert oldest[0]["id"] not in [item["id"] for item in rest]


class _ConflictRow:
    tenant_id = "tenant-a"
    device_id = "device-a"
    peer_key = "peer-a"
    platform_count = 2


class _FakeResult:
    def fetchall(self):
        return [_ConflictRow()]


class _FakeConnection:
    def execute(self, _statement):
        return _FakeResult()


def test_im_thread_platform_migration_rejects_conflicts(monkeypatch) -> None:
    import importlib.util
    from pathlib import Path

    migration = (
        Path(__file__).resolve().parents[2]
        / "services/control-api/migrations/versions/20260923_0033_im_thread_platform_key.py"
    )
    spec = importlib.util.spec_from_file_location("im_thread_platform_key", migration)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module.op, "get_bind", lambda: _FakeConnection())
    with pytest.raises(RuntimeError, match="platform conflict"):
        module._assert_one_platform_per_legacy_key()


def test_postgres_migration_chain_including_platform_key(pg_url):  # noqa: F811
    from alembic.config import Config

    config = Config(str(Path(__file__).resolve().parents[2] / "services/control-api/alembic.ini"))
    config.set_main_option("sqlalchemy.url", pg_url)
    command.upgrade(config, "head")
    command.downgrade(config, "20260920_0032")
    command.upgrade(config, "head")


def test_im_thread_platform_migration_round_trip_and_downgrade_guard(tmp_path) -> None:
    database_path = tmp_path / "im-platform-key.db"
    config = migration_config(database_path)
    command.upgrade(config, "head")

    with sqlite3.connect(database_path) as connection:
        index_columns = {
            str(row[1]): [
                str(column[2]) for column in connection.execute(f"PRAGMA index_info('{row[1]}')")
            ]
            for row in connection.execute("PRAGMA index_list('im_thread')")
            if int(row[2]) == 1
        }
        assert ["tenant_id", "device_id", "platform", "peer_key"] in index_columns.values()
        for platform, suffix in (("xianyu", "1"), ("xhs", "2")):
            connection.execute(
                """
                INSERT INTO im_thread (
                    id, tenant_id, device_id, platform, peer_key, peer_name,
                    last_message_at, last_direction, unread_count, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 'same-peer', 'same-peer', ?, 'IN', 0, ?, ?)
                """,
                (
                    f"00000000-0000-7000-8000-00000000330{suffix}",
                    "00000000-0000-7000-8000-000000000111",
                    "00000000-0000-7000-8000-000000000222",
                    platform,
                    "2026-09-23 00:00:00+00:00",
                    "2026-09-23 00:00:00+00:00",
                    "2026-09-23 00:00:00+00:00",
                ),
            )
        connection.commit()

    with pytest.raises(RuntimeError, match="platform conflict"):
        command.downgrade(config, "20260920_0032")
    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT count(*) FROM im_thread").fetchone() == (2,)


READ_ONLY_ROLES = ("viewer", "content_editor", "publisher", "approver", "automation_developer")


async def test_im_write_endpoints_require_device_control(api):  # noqa: F811
    """PUT im/config and POST :reply are device writes gated on device.control.

    Read-only roles keep full inbox read access but must not change monitoring
    configuration nor trigger an outbound message on a real device.
    """
    client, _app = api
    device = await create_direct_device(client, "im-acl-dev")
    auth = await _enroll(client, device, "im-acl-instance")
    when = datetime.now(UTC).replace(microsecond=0)
    await _push(client, auth, peer="buyer_acl", text="还在吗", when=when)
    thread = (await client.get("/api/v1/im/threads", headers=identity())).json()["items"][0]

    for role in READ_ONLY_ROLES:
        read_only = identity(role=role)
        # Read paths stay open for every role.
        threads = await client.get("/api/v1/im/threads", headers=read_only)
        assert threads.status_code == 200, (role, threads.text)
        config = await client.get(
            "/api/v1/im/config", params={"deviceId": device}, headers=read_only
        )
        assert config.status_code == 200, (role, config.text)
        # Write paths are rejected before any state changes.
        denied_config = await client.put(
            "/api/v1/im/config",
            params={"deviceId": device},
            headers=read_only,
            json={
                "enabled": False,
                "platforms": ["xianyu"],
                "mode": "DUTY",
                "dutyStart": "09:00",
                "dutyEnd": "23:00",
            },
        )
        assert denied_config.status_code == 403, role
        denied_reply = await client.post(
            f"/api/v1/im/threads/{thread['id']}:reply",
            headers=read_only,
            json={"text": "越权回复"},
        )
        assert denied_reply.status_code == 403, role

    # device.control holders (device_operator, security_admin, system_service) may write.
    for role in ("device_operator", "security_admin", "system_service"):
        allowed = await client.put(
            "/api/v1/im/config",
            params={"deviceId": device},
            headers=identity(role=role),
            json={
                "enabled": True,
                "platforms": ["xianyu", "douyin"],
                "mode": "DUTY",
                "dutyStart": "08:00",
                "dutyEnd": "22:00",
            },
        )
        assert allowed.status_code == 200, (role, allowed.text)
        assert allowed.json()["platforms"] == ["xianyu", "douyin"]

    approved = await client.post(
        f"/api/v1/im/threads/{thread['id']}:reply",
        headers=identity(role="device_operator"),
        json={"text": "在的"},
    )
    assert approved.status_code == 201, approved.text
    assert approved.json()["taskId"]

    # The denied attempts left no OUT message and no task behind.
    from cloudctl_api.db import ImMessageRow, MobileTaskRow
    from sqlalchemy import select

    async with _app.state.database.unit_of_work() as session:
        outbound = list(
            await session.scalars(
                select(ImMessageRow).where(ImMessageRow.thread_id == thread["id"])
            )
        )
        assert [row.direction for row in outbound].count("OUT") == 1
        tasks = list(await session.scalars(select(MobileTaskRow)))
        assert len(tasks) == 1
