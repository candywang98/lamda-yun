"""Live session slice 1 (p10-live/20260913.1): state machine, audits, single writer."""

from __future__ import annotations

import time

from cloudctl_api.live import LiveSession

from test_p14_recipe_versions import (  # noqa: F401 - pytest fixture injection
    api,
    isolated_postgres,
    pg_url,
)
from test_platform_tasks import _enroll, create_direct_device, identity


def test_input_guard_rejects_stale_seq_and_bad_state():
    live = LiveSession("s1", "d1", "t1")
    assert live.check_input("tap", 1, time.monotonic()) == "NOT_REMOTE"
    live.state = "REMOTE"
    assert live.check_input("tap", 1, time.monotonic()) is None
    assert live.check_input("tap", 1, time.monotonic()) == "SEQ_STALE"
    assert live.check_input("tap", 0, time.monotonic()) == "SEQ_STALE"
    assert live.check_input("pinch", 2, time.monotonic()) == "BAD_KIND"
    assert live.check_input("tap", 2, time.monotonic()) is None


def test_input_guard_enforces_rate_limit():
    live = LiveSession("s2", "d1", "t1")
    live.state = "REMOTE"
    now = time.monotonic()
    accepted = 0
    for seq in range(1, 15):
        if live.check_input("tap", seq, now) is None:
            accepted += 1
    assert accepted == 10


def test_session_expiry_rules():
    live = LiveSession("s3", "d1", "t1")
    live.opened_monotonic = time.monotonic() - 31 * 60
    assert live.is_expired(time.monotonic()) == "TIMEOUT"
    fresh = LiveSession("s4", "d1", "t1")
    assert fresh.is_expired(time.monotonic()) is None
    fresh.last_frame_monotonic = time.monotonic() - 45.0
    assert fresh.is_expired(time.monotonic()) == "FRAME_STALLED"
    fresh.state = "CLOSED"
    assert fresh.is_expired(time.monotonic()) is None


async def test_session_lifecycle_audits_and_single_writer(api):  # noqa: F811
    client, app = api
    device = await create_direct_device(client, "live-dev")
    auth = await _enroll(client, device, "live-instance")

    opened = await client.post(f"/api/v1/devices/{device}/live", headers=identity())
    assert opened.status_code in (200, 201), opened.text
    sid = opened.json()["sessionId"]
    assert opened.json()["state"] == "VIEWING"

    duplicate = await client.post(f"/api/v1/devices/{device}/live", headers=identity())
    assert duplicate.status_code == 409
    assert "SESSION_EXISTS" in duplicate.text

    taken = await client.post(
        f"/api/v1/devices/{device}/live/{sid}:take-control", headers=identity()
    )
    assert taken.status_code == 200, taken.text
    assert taken.json()["state"] == "REMOTE"

    # While REMOTE, task claims are refused with DEVICE_REMOTE.
    created = await client.post(
        "/api/v1/mobile/tasks",
        headers={**identity(), "Idempotency-Key": f"live-claim-{device[:20]}"},
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
    refused = await client.post(
        "/companion/v2/tasks/claim", headers=auth, json={"leaseSeconds": 60}
    )
    assert refused.status_code == 409
    assert "DEVICE_REMOTE" in refused.text

    released = await client.post(
        f"/api/v1/devices/{device}/live/{sid}:release", headers=identity()
    )
    assert released.status_code == 200
    assert released.json()["state"] == "VIEWING"

    status = await client.get(f"/api/v1/devices/{device}/live/{sid}", headers=identity())
    assert status.status_code == 200
    assert status.json()["state"] == "VIEWING"

    stopped = await client.post(
        f"/api/v1/devices/{device}/live/{sid}:stop", headers=identity()
    )
    assert stopped.status_code == 200
    assert stopped.json()["state"] == "CLOSED"

    # Audits cover open / take-control / release / close.manual.
    from cloudctl_api.db import AuditEventRow
    from sqlalchemy import select

    async with app.state.database.unit_of_work() as session:
        actions = list(
            await session.scalars(
                select(AuditEventRow.action).where(AuditEventRow.resource_id == sid)
            )
        )
    assert set(actions) >= {
        "live.session.open",
        "live.session.take-control",
        "live.session.release",
        "live.session.close.manual",
    }
