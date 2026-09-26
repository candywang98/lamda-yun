"""I10 (fleet-first-20260916.1): IM duty/reply single-writer, inbound dedupe,
reply boundary and cancel/outbox consistency at the fleet level.

The device-side halves live in the companion im/ package unit tests
(DutyWriteArbitration, ImMonitor retransmission window, ImReplyBoundary);
these integration tests pin the cloud halves that the device behaviour relies on:

  - single writer: a RUNNING reply task owns the device — no second IM reply
    may even be created (409 DEVICE_BUSY), and no second task/OUT row exists;
  - cancel consistency: cancelling a reply task (queued or RUNNING) settles the
    cloud outbox to FAILED; late straggler reports from the device (heartbeat /
    complete / fail on the revoked lease) are rejected and cannot resurrect a
    pending send; duplicate cancels are idempotent; DELIVERED is absorbing;
  - inbound dedupe: retransmitted pushes never create a second IN row and thus
    never re-arm a second reply;
  - fleet ownership: only the bound device can drive a reply task.
"""

from __future__ import annotations

from datetime import UTC, datetime

from test_p14_recipe_versions import (  # noqa: F401 - pytest fixture injection
    api,
    claim,
    isolated_postgres,
    pg_url,
)
from test_platform_tasks import _enroll, create_direct_device, identity


def _message(peer: str, text: str, when: datetime) -> dict:
    return {
        "platform": "xianyu",
        "peerKey": peer,
        "peerName": peer,
        "text": text,
        "occurredAt": when.isoformat(),
    }


async def _push(client, auth, peer: str, text: str, when: datetime) -> dict:
    response = await client.post(
        "/companion/v2/im/messages",
        headers=auth,
        json={"messages": [_message(peer, text, when)]},
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _thread_of(client, peer: str) -> dict:
    threads = (await client.get("/api/v1/im/threads", headers=identity())).json()["items"]
    return next(thread for thread in threads if thread["peerKey"] == peer)


async def _messages(client, thread_id: str) -> list[dict]:
    return (
        await client.get(f"/api/v1/im/threads/{thread_id}/messages", headers=identity())
    ).json()["items"]


async def _outbox_rows(app, task_id: str) -> list:
    from cloudctl_api.db import ImMessageRow
    from sqlalchemy import select

    async with app.state.database.unit_of_work() as session:
        return list(
            await session.scalars(select(ImMessageRow).where(ImMessageRow.reply_task_id == task_id))
        )


async def _start_reply(client, auth, thread_id: str, text: str = "在的，可以拍") -> str:
    reply = await client.post(
        f"/api/v1/im/threads/{thread_id}:reply", headers=identity(), json={"text": text}
    )
    assert reply.status_code == 201, reply.text
    task_id = reply.json()["taskId"]
    claimed = await claim(client, auth)
    assert claimed["taskId"] == task_id
    started = await client.post(
        f"/companion/v2/tasks/{task_id}/heartbeat",
        headers=auth,
        json={"leaseId": claimed["leaseId"], "currentStep": 0},
    )
    assert started.status_code == 200, started.text
    return task_id


async def test_running_reply_task_is_the_single_writer(api):  # noqa: F811
    """仲裁（云端一半）：回复任务 RUNNING 期间，设备被任务独占——任何线程的
    第二条回复都不能创建，不会留下第二个任务或 OUT 行。发品任务与值班同时
    触发时设备端由 DutyWriteArbitration 让位（见 companion 单测），云端同一
    时刻连第二条 IM 写入都不产生。"""
    client, app = api
    device = await create_direct_device(client, "i10-single-dev")
    auth = await _enroll(client, device, "i10-single-inst")
    when = datetime.now(UTC).replace(microsecond=0)
    await _push(client, auth, peer="i10_buyer_a", text="还在吗", when=when)
    await _push(client, auth, peer="i10_buyer_b", text="能便宜点吗", when=when)
    thread_a = await _thread_of(client, "i10_buyer_a")
    thread_b = await _thread_of(client, "i10_buyer_b")

    running_task = await _start_reply(client, auth, thread_a["id"], "在的")
    assert running_task

    # Same thread: the running reply's fresh OUT trips the per-thread cooldown
    # (no second reply into one conversation), and a DIFFERENT thread is
    # refused because the device is owned by the RUNNING task — either way
    # exactly one writer, no second task or OUT row appears.
    same_thread = await client.post(
        f"/api/v1/im/threads/{thread_a['id']}:reply",
        headers=identity(),
        json={"text": "第二条回复"},
    )
    assert same_thread.status_code == 409, same_thread.text
    assert "THREAD_REPLY_RATE_LIMITED" in same_thread.text
    other_thread = await client.post(
        f"/api/v1/im/threads/{thread_b['id']}:reply",
        headers=identity(),
        json={"text": "另一条回复"},
    )
    assert other_thread.status_code == 409, other_thread.text
    assert "DEVICE_BUSY" in other_thread.text

    from cloudctl_api.db import ImMessageRow, MobileTaskRow
    from sqlalchemy import select

    async with app.state.database.unit_of_work() as session:
        tasks = list(await session.scalars(select(MobileTaskRow)))
        assert len(tasks) == 1
        outs = list(
            await session.scalars(select(ImMessageRow).where(ImMessageRow.direction == "OUT"))
        )
        assert len(outs) == 1
        assert outs[0].delivery_state == "PENDING"


async def test_cancel_running_reply_settles_outbox_and_rejects_stragglers(api):  # noqa: F811
    """取消一致（核心场景）：RUNNING 回复被取消后走 A14 控制-面语义——云端先
    CANCEL_REQUESTED，设备确认已放弃待发（CANCEL_APPLIED ack，本地不再有待发）
    后任务收敛 CANCELLED、outbox 落 FAILED；设备迟到的 straggler 报告（心跳/
    完成/失败）全部 409，不能把 outbox 拉回 PENDING/DELIVERED；重复取消幂等。"""
    client, app = api
    device = await create_direct_device(client, "i10-cancel-dev")
    auth = await _enroll(client, device, "i10-cancel-inst")
    when = datetime.now(UTC).replace(microsecond=0)
    await _push(client, auth, peer="i10_cancel_buyer", text="发货了吗", when=when)
    thread = await _thread_of(client, "i10_cancel_buyer")

    reply = await client.post(
        f"/api/v1/im/threads/{thread['id']}:reply", headers=identity(), json={"text": "今天发"}
    )
    assert reply.status_code == 201, reply.text
    task_id = reply.json()["taskId"]
    claimed = await claim(client, auth)
    assert claimed["taskId"] == task_id
    started = await client.post(
        f"/companion/v2/tasks/{task_id}/heartbeat",
        headers=auth,
        json={"leaseId": claimed["leaseId"], "currentStep": 0},
    )
    assert started.status_code == 200, started.text
    assert (await _messages(client, thread["id"]))[-1]["deliveryState"] == "PENDING"

    # Operator retracts: for a RUNNING task the cancel is first REQUESTED and
    # only becomes terminal when the device acks it dropped the pending send.
    cancelled = await client.post(
        f"/api/v1/platform-tasks/{task_id}:cancel",
        headers=identity(),
        json={"reason": "operator retracted the running reply"},
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["state"] == "CANCEL_REQUESTED"

    # Device-side pending send is dropped locally, then acked — the cloud task
    # and outbox converge in the same step (no window with a pending send).
    ack = await client.post(
        "/companion/v2/control/ack",
        headers=auth,
        json={"taskId": task_id, "result": "CANCEL_APPLIED", "reason": "local send dropped"},
    )
    assert ack.status_code == 200, ack.text
    assert ack.json()["result"] == "CANCEL_APPLIED"

    # Cloud outbox settled to FAILED with the ack.
    items = await _messages(client, thread["id"])
    out = next(item for item in items if item["direction"] == "OUT")
    assert out["deliveryState"] == "FAILED"
    assert out["replyTaskId"] == task_id
    assert [row.delivery_state for row in await _outbox_rows(app, task_id)] == ["FAILED"]

    # Local stragglers: the lease was revoked with the cancel, so late
    # heartbeat/complete/fail reports are all rejected — the settled outbox
    # cannot be resurrected into a pending (or delivered) send.
    late_heartbeat = await client.post(
        f"/companion/v2/tasks/{task_id}/heartbeat",
        headers=auth,
        json={"leaseId": claimed["leaseId"], "currentStep": 2},
    )
    assert late_heartbeat.status_code == 409, late_heartbeat.text
    late_complete = await client.post(
        f"/companion/v2/tasks/{task_id}/complete",
        headers=auth,
        json={"leaseId": claimed["leaseId"], "result": {}},
    )
    assert late_complete.status_code == 409, late_complete.text
    late_fail = await client.post(
        f"/companion/v2/tasks/{task_id}/fail",
        headers=auth,
        json={"leaseId": claimed["leaseId"], "errorCode": "STEP_TIMEOUT", "detail": "late"},
    )
    assert late_fail.status_code == 409, late_fail.text

    # Cancel is idempotent; the outbox stays FAILED.
    again = await client.post(
        f"/api/v1/platform-tasks/{task_id}:cancel",
        headers=identity(),
        json={"reason": "duplicate cancel event"},
    )
    assert again.status_code == 200, again.text
    assert again.json()["state"] == "CANCELLED"
    assert [row.delivery_state for row in await _outbox_rows(app, task_id)] == ["FAILED"]

    # A replayed device ack (retry after the converged state) stays idempotent.
    replayed_ack = await client.post(
        "/companion/v2/control/ack",
        headers=auth,
        json={"taskId": task_id, "result": "CANCEL_APPLIED", "reason": "retry"},
    )
    assert replayed_ack.status_code == 200, replayed_ack.text
    assert [row.delivery_state for row in await _outbox_rows(app, task_id)] == ["FAILED"]

    from cloudctl_api.db import MobileTaskRow

    async with app.state.database.unit_of_work() as session:
        row = await session.get(MobileTaskRow, task_id)
        assert (row.status, row.business_state) == ("FAILED", "CANCELLED")
        assert row.lease_id is None


async def test_retransmitted_push_never_re_arms_a_second_reply(api):  # noqa: F811
    """去重（云端一半）：同一推送（同 occurredAt）重传只落一条 IN；重传不会
    重建会话/未读，也不会让同一个买家触发第二条回复任务。"""
    client, app = api
    device = await create_direct_device(client, "i10-dup-dev")
    auth = await _enroll(client, device, "i10-dup-inst")
    when = datetime.now(UTC).replace(microsecond=0)

    first = await _push(client, auth, peer="i10_dup_buyer", text="这个还有货吗", when=when)
    assert first == {"accepted": 1, "duplicates": 0}
    # Same push retransmitted (companion outbox retry re-POSTs the same batch).
    for _ in range(2):
        retransmitted = await _push(
            client, auth, peer="i10_dup_buyer", text="这个还有货吗", when=when
        )
        assert retransmitted == {"accepted": 0, "duplicates": 1}

    thread = await _thread_of(client, "i10_dup_buyer")
    items = await _messages(client, thread["id"])
    assert [item["direction"] for item in items] == ["IN"]
    assert thread["unreadCount"] == 1

    # One reply task is created and claimed; a retransmission after the task
    # failed cannot re-arm a second reply (no new IN, rate-limited OUT).
    reply = await client.post(
        f"/api/v1/im/threads/{thread['id']}:reply", headers=identity(), json={"text": "有货"}
    )
    assert reply.status_code == 201, reply.text
    task_id = reply.json()["taskId"]
    claimed = await claim(client, auth)
    assert claimed["taskId"] == task_id
    failed = await client.post(
        f"/companion/v2/tasks/{task_id}/fail",
        headers=auth,
        json={"leaseId": claimed["leaseId"], "errorCode": "STEP_TIMEOUT", "detail": "list changed"},
    )
    assert failed.status_code == 200, failed.text

    retransmitted = await _push(client, auth, peer="i10_dup_buyer", text="这个还有货吗", when=when)
    assert retransmitted == {"accepted": 0, "duplicates": 1}
    second_reply = await client.post(
        f"/api/v1/im/threads/{thread['id']}:reply", headers=identity(), json={"text": "还有"}
    )
    assert second_reply.status_code == 409, second_reply.text
    assert "THREAD_REPLY_RATE_LIMITED" in second_reply.text

    from cloudctl_api.db import ImMessageRow, MobileTaskRow
    from sqlalchemy import select

    async with app.state.database.unit_of_work() as session:
        ins = list(
            await session.scalars(
                select(ImMessageRow).where(
                    ImMessageRow.thread_id == thread["id"], ImMessageRow.direction == "IN"
                )
            )
        )
        assert len(ins) == 1
        tasks = list(await session.scalars(select(MobileTaskRow)))
        assert len(tasks) == 1


async def test_reply_task_is_drivable_only_by_its_bound_device(api):  # noqa: F811
    """舰队所有权：回复任务只能由绑定的设备驱动；另一台设备的 companion
    认领不到它，也不能对它上报心跳/完成（fail-closed 404/204）。"""
    client, _app = api
    device_a = await create_direct_device(client, "i10-owner-a")
    auth_a = await _enroll(client, device_a, "i10-owner-a-inst")
    device_b = await create_direct_device(client, "i10-owner-b")
    auth_b = await _enroll(client, device_b, "i10-owner-b-inst")
    when = datetime.now(UTC).replace(microsecond=0)
    await _push(client, auth_a, peer="i10_owner_buyer", text="在吗", when=when)
    thread = await _thread_of(client, "i10_owner_buyer")

    reply = await client.post(
        f"/api/v1/im/threads/{thread['id']}:reply", headers=identity(), json={"text": "在的"}
    )
    assert reply.status_code == 201, reply.text
    task_id = reply.json()["taskId"]

    # Device B claims nothing: the task belongs to device A.
    claim_b = await client.post(
        "/companion/v2/tasks/claim", headers=auth_b, json={"leaseSeconds": 60}
    )
    assert claim_b.status_code == 204, claim_b.text

    # Device B cannot drive A's task by id (ownership fail-closed).
    heartbeat_b = await client.post(
        f"/companion/v2/tasks/{task_id}/heartbeat",
        headers=auth_b,
        json={"leaseId": "any-lease", "currentStep": 0},
    )
    assert heartbeat_b.status_code == 404, heartbeat_b.text
    complete_b = await client.post(
        f"/companion/v2/tasks/{task_id}/complete",
        headers=auth_b,
        json={"leaseId": "any-lease", "result": {}},
    )
    assert complete_b.status_code == 404, complete_b.text

    # The bound device still owns it and the outbox stays untouched by B.
    claimed_a = await claim(client, auth_a)
    assert claimed_a["taskId"] == task_id
