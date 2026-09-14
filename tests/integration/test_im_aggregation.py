"""IM aggregation slice 1 (pa-im/20260913.1): ingest, inbox, gated reply."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from test_p14_recipe_versions import (  # noqa: F401 - pytest fixture injection
    api,
    isolated_postgres,
    pg_url,
)
from test_platform_tasks import _enroll, create_direct_device, identity


def _message(peer: str, text: str, when: datetime, name: str | None = None):
    return {
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

    messages = (
        await client.get(f"/api/v1/im/threads/{thread['id']}/messages", headers=identity())
    ).json()["items"]
    assert [m["text"] for m in messages] == ["你好，还在吗？", "第二条"]

    marked = await client.post(
        f"/api/v1/im/threads/{thread['id']}:mark-read", headers=identity()
    )
    assert marked.status_code == 200
    assert marked.json()["unreadCount"] == 0


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
            "ui.find", "ui.tap", "ui.tapText", "ui.wait", "ui.input", "ui.tap",
        ]
        tap_text = next(step for step in real_steps if step["action"] == "ui.tapText")
        assert tap_text["value"] == "buyer_b"

    # The reply task must be claimable by the bound companion.
    from test_p14_recipe_versions import claim

    claimed = await claim(client, auth)
    assert claimed["taskId"] == task_id

    # Second reply within the cooldown is rejected even after the task finished.
    await client.post(f"/companion/v2/tasks/{task_id}/heartbeat", headers=auth,
                      json={"leaseId": claimed["leaseId"], "currentStep": 0})
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
                {"stepId": "idle", "timeoutMs": 8000, "action": "ui.wait",
                 "locatorRef": "xianyu_home_sell", "condition": "EXISTS", "pollMs": 200},
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

    default = await client.get(
        "/api/v1/im/config", params={"deviceId": device}, headers=identity()
    )
    assert default.status_code == 200
    assert default.json()["platforms"] == ["xianyu"]
    assert default.json()["mode"] == "NOTIFICATION"

    saved = await client.put(
        "/api/v1/im/config",
        params={"deviceId": device},
        headers=identity(),
        json={"enabled": True, "platforms": ["xianyu", "xhs", "douyin"],
              "mode": "DUTY", "dutyStart": "08:30", "dutyEnd": "22:00"},
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
