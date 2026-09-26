"""Frozen notification-classification contract on SQLite and real disposable PostgreSQL."""

import asyncio
import json
import sqlite3
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

from alembic import command
from cloudctl_api.db import AuditEventRow, ImClassificationRow, ImMessageRow, MobileTaskRow
from cloudctl_api.im_classifier import MessageAssessment
from cloudctl_api.im_observer import InboundObservation
from sqlalchemy import func, select
from test_control_api_migrations import migration_config
from test_im_aggregation import _message, _push
from test_p14_recipe_versions import api, isolated_postgres, pg_url  # noqa: F401
from test_platform_tasks import _enroll, create_direct_device, identity


async def setup(client):
    device = await create_direct_device(client, "classification")
    auth = await _enroll(client, device, "classification-instance")
    return device, auth


async def threads(client, **params):
    response = await client.get("/api/v1/im/threads", headers=identity(), params=params)
    assert response.status_code == 200, response.text
    return response.json()


async def messages(client, thread, **params):
    response = await client.get(
        f"/api/v1/im/threads/{thread}/messages", headers=identity(), params=params
    )
    assert response.status_code == 200, response.text
    return response.json()["items"]


async def test_metadata_legacy_validation_and_dedupe(api):  # noqa: F811
    client, app = api
    _, auth = await setup(client)
    when = datetime.now(UTC)
    item = _message("buyer", "发来一条新消息", when)
    metadata = {"packageName": "com.taobao.idlefish", "channelId": "push", "category": "msg"}
    item["notificationMetadata"] = metadata
    result = await client.post("/companion/v2/im/messages", headers=auth, json={"messages": [item]})
    assert result.json()["accepted"] == 1
    thread = (await threads(client))["items"][0]
    message = (await messages(client, thread["id"]))[0]
    assert message["notificationMetadata"] == metadata
    assert message["classification"]["category"] == "HUMAN_MESSAGE"
    assert message["classification"]["confidence"] is None
    assert message["classification"]["source"] == "RULE"
    for bad in (
        {"extra": True},
        {"channelId": "x" * 257},
        {"category": "x" * 65},
        {"packageName": "other.app"},
    ):
        item["notificationMetadata"] = bad
        result = await client.post(
            "/companion/v2/im/messages", headers=auth, json={"messages": [item]}
        )
        assert result.status_code == 422
    item["notificationMetadata"] = None
    result = await client.post("/companion/v2/im/messages", headers=auth, json={"messages": [item]})
    assert result.json() == {"accepted": 0, "duplicates": 1}
    assert (await messages(client, thread["id"]))[0]["notificationMetadata"] == metadata
    async with app.state.database.unit_of_work() as session:
        assert await session.scalar(select(func.count()).select_from(ImMessageRow)) == 1


async def test_mixed_buckets_filter_before_pagination_and_count_full_result(api):  # noqa: F811
    client, _ = api
    device, auth = await setup(client)
    when = datetime.now(UTC).replace(microsecond=0)
    await _push(client, auth, "mixed", "发来一条新消息", when)
    await _push(client, auth, "second", "发来一条新消息", when + timedelta(seconds=1))
    # Same peer, later official notification: only the notice bucket summary changes.
    item = _message("mixed", "订单已发货", when + timedelta(seconds=10), "闲鱼官方")
    assert (
        await client.post("/companion/v2/im/messages", headers=auth, json={"messages": [item]})
    ).status_code == 200
    await _push(client, auth, "mixed", "内容不确定", when + timedelta(seconds=20))
    first = await threads(client, bucket="user", limit=1, deviceId=device)
    assert first["bucketCounts"] == {"all": 2, "user": 2, "notice": 1, "review": 1}
    assert first["items"][0]["peerKey"] == "second"
    second = await threads(client, bucket="user", after=first["items"][0]["id"], limit=1)
    assert second["bucketCounts"] == first["bucketCounts"]
    assert second["items"][0]["lastMessageText"] == "发来一条新消息"
    tid = second["items"][0]["id"]
    assert [x["text"] for x in await messages(client, tid, bucket="notice")] == ["订单已发货"]
    assert [x["text"] for x in await messages(client, tid, bucket="review")] == ["内容不确定"]
    assert len(await messages(client, tid, bucket="all")) == 3
    result = await client.get(
        "/api/v1/im/threads",
        headers=identity(),
        params={"deviceId": "different-device", "after": tid, "bucket": "user"},
    )
    assert result.status_code == 404


async def test_correction_reset_acl_version_audit_and_no_sends(api):  # noqa: F811
    client, app = api
    _, auth = await setup(client)
    await _push(client, auth, text="发来一条新消息")
    tid = (await threads(client))["items"][0]["id"]
    message = (await messages(client, tid))[0]
    url = f"/api/v1/im/messages/{message['id']}:classify"
    payload = {"category": "PROMOTION", "expectedVersion": message["classification"]["version"]}
    readonly = await client.post(url, headers=identity(role="auditor"), json=payload)
    assert readonly.status_code == 403
    foreign = {**identity(), "X-Tenant-Id": "00000000-0000-7000-8000-000000009999"}
    assert (await client.post(url, headers=foreign, json=payload)).status_code == 404
    retry_url = url.replace(":classify", ":reclassify")
    retry_body = {"expectedVersion": payload["expectedVersion"]}
    assert (
        await client.post(retry_url, headers=identity(role="auditor"), json=retry_body)
    ).status_code == 403
    assert (await client.post(retry_url, headers=foreign, json=retry_body)).status_code == 404
    result = await client.post(url, headers=identity(), json=payload)
    assert result.status_code == 200, result.text
    fixed = result.json()
    assert fixed["classification"]["source"] == "MANUAL"
    assert (await threads(client, bucket="user"))["count"] == 0
    assert (await client.post(url, headers=identity(), json=payload)).status_code == 409
    payload = {"category": None, "expectedVersion": fixed["classification"]["version"]}
    reset = (await client.post(url, headers=identity(), json=payload)).json()
    assert reset["classification"]["category"] == "HUMAN_MESSAGE"
    assert reset["classification"]["source"] == "RULE"
    async with app.state.database.unit_of_work() as session:
        assert await session.scalar(select(func.count()).select_from(MobileTaskRow)) == 0
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ImMessageRow)
                .where(ImMessageRow.direction == "OUT")
            )
            == 0
        )
        audits = list(
            await session.scalars(
                select(AuditEventRow).where(AuditEventRow.action == "im.message.classify")
            )
        )
        assert len(audits) == 2
        assert message["text"] not in json.dumps(
            [x.metadata_json for x in audits], ensure_ascii=False
        )


async def test_manual_override_survives_async_model_and_raw_low_confidence(api):  # noqa: F811
    client, app = api
    device, auth = await setup(client)
    observer = app.state.im_observer
    observer.classifier.settings = observer.classifier.settings.model_copy(
        update={
            "im_classifier_enabled": True,
            "im_classifier_device_ids": [device],
        }
    )
    started, finish = asyncio.Event(), asyncio.Event()

    async def blocked(**kwargs):
        started.set()
        await finish.wait()
        return MessageAssessment(
            predicted_category="PROMOTION", confidence=0.39, status="NEEDS_REVIEW"
        )

    observer.classifier.classify = AsyncMock(side_effect=blocked)
    observer.start()
    await _push(client, auth, text="需要模型判断")
    await asyncio.wait_for(started.wait(), 2)
    tid = (await threads(client))["items"][0]["id"]
    message = (await messages(client, tid))[0]
    url = f"/api/v1/im/messages/{message['id']}:classify"
    response = await client.post(
        url,
        headers=identity(),
        json={
            "category": "HUMAN_MESSAGE",
            "expectedVersion": message["classification"]["version"],
        },
    )
    assert response.status_code == 200
    finish.set()
    await asyncio.wait_for(observer._queue.join(), 2)
    result = (await messages(client, tid))[0]["classification"]
    assert result["category"] == "HUMAN_MESSAGE"
    assert result["source"] == "MANUAL"
    assert result["predictedCategory"] == "PROMOTION"
    assert result["confidence"] == 0.39
    assert result["modelStatus"] == "NEEDS_REVIEW"
    reset = await client.post(
        url,
        headers=identity(),
        json={
            "category": None,
            "expectedVersion": result["version"],
        },
    )
    assert reset.json()["classification"]["category"] == "UNKNOWN"


async def test_legacy_history_and_reclassify_generation_preserve_manual(api):  # noqa: F811
    client, app = api
    device, auth = await setup(client)
    await _push(client, auth, text="发来一条新消息")
    tid = (await threads(client))["items"][0]["id"]
    message = (await messages(client, tid))[0]
    # Simulate history predating the additive sidecar migration, test database only.
    async with app.state.database.unit_of_work() as session:
        row = await session.get(ImClassificationRow, message["id"])
        await session.delete(row)
    legacy = (await messages(client, tid))[0]
    assert legacy["classification"]["version"] == 0
    assert (await threads(client, bucket="review"))["count"] == 1
    url = f"/api/v1/im/messages/{message['id']}"
    fixed = (
        await client.post(
            url + ":classify",
            headers=identity(),
            json={
                "category": "SYSTEM_NOTICE",
                "expectedVersion": 0,
            },
        )
    ).json()
    retry = await client.post(
        url + ":reclassify",
        headers=identity(),
        json={
            "expectedVersion": fixed["classification"]["version"],
        },
    )
    assert retry.status_code == 200
    assert retry.json()["classification"]["category"] == "SYSTEM_NOTICE"
    assert retry.json()["classification"]["ruleCode"] == "NAMED_PEER_MESSAGE_SUMMARY"
    before = retry.json()["classification"]
    await app.state.im_service._persist_assessment(
        InboundObservation(message["id"], device, "xianyu", "buyer", "text", generation=1),
        MessageAssessment(
            category="PROMOTION",
            predicted_category="PROMOTION",
            confidence=1.0,
            status="CLASSIFIED",
        ),
    )
    assert (await messages(client, tid))[0]["classification"] == before


async def test_model_storage_failure_does_not_fail_committed_intake(api):  # noqa: F811
    client, app = api
    _, auth = await setup(client)
    app.state.im_observer.persist = AsyncMock(side_effect=RuntimeError("private provider data"))
    assert (await _push(client, auth))["accepted"] == 1
    assert (await threads(client))["count"] == 1


async def test_reclassification_uses_original_notification_title(api):  # noqa: F811
    client, _ = api
    _, auth = await setup(client)
    when = datetime.now(UTC)
    await _push(client, auth, "same-peer", "发来一条新消息", when)
    tid = (await threads(client))["items"][0]["id"]
    original = (await messages(client, tid))[0]
    item = _message("same-peer", "订单已发货", when + timedelta(seconds=1), "闲鱼官方")
    await client.post("/companion/v2/im/messages", headers=auth, json={"messages": [item]})
    result = await client.post(
        f"/api/v1/im/messages/{original['id']}:reclassify",
        headers=identity(),
        json={"expectedVersion": original["classification"]["version"]},
    )
    assert result.status_code == 200
    assert result.json()["classification"]["category"] == "HUMAN_MESSAGE"


async def test_concurrent_first_corrections_use_original_message_lock(api):  # noqa: F811
    client, app = api
    if app.state.database.engine.dialect.name != "postgresql":
        return  # SELECT FOR UPDATE concurrency is verified against PostgreSQL.
    _, auth = await setup(client)
    await _push(client, auth)
    tid = (await threads(client))["items"][0]["id"]
    message = (await messages(client, tid))[0]
    async with app.state.database.unit_of_work() as session:
        await session.delete(await session.get(ImClassificationRow, message["id"]))
    responses = await asyncio.gather(
        *[
            client.post(
                f"/api/v1/im/messages/{message['id']}:classify",
                headers=identity(),
                json={"category": category, "expectedVersion": 0},
            )
            for category in ("HUMAN_MESSAGE", "SYSTEM_NOTICE")
        ]
    )
    assert sorted(response.status_code for response in responses) == [200, 409]


def test_additive_migration_keeps_original_message_rows(tmp_path):
    path = tmp_path / "classification.db"
    config = migration_config(path)
    command.upgrade(config, "20260923_0033")
    with sqlite3.connect(path) as db:
        db.execute(
            "INSERT INTO im_message (id, tenant_id, thread_id, direction, content_type, "
            "text_content, occurred_at, dedupe_key, delivery_state, created_at) "
            "VALUES ('original', 'tenant', 'thread', 'IN', 'TEXT', 'private', "
            "'2026-09-26', 'original-key', 'DELIVERED', '2026-09-26')"
        )
        before = db.execute("SELECT * FROM im_message").fetchall()
    command.upgrade(config, "head")
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT count(*) FROM im_message_classification").fetchone()[0] == 0
        assert db.execute("SELECT * FROM im_message").fetchall() == before
    command.downgrade(config, "20260923_0033")
    command.upgrade(config, "head")
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT * FROM im_message").fetchall() == before
