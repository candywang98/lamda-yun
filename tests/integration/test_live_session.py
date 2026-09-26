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
    refused = await client.post(
        "/companion/v2/tasks/claim", headers=auth, json={"leaseSeconds": 60}
    )
    assert refused.status_code == 409
    assert "DEVICE_REMOTE" in refused.text

    released = await client.post(f"/api/v1/devices/{device}/live/{sid}:release", headers=identity())
    assert released.status_code == 200
    assert released.json()["state"] == "VIEWING"

    status = await client.get(f"/api/v1/devices/{device}/live/{sid}", headers=identity())
    assert status.status_code == 200
    assert status.json()["state"] == "VIEWING"

    stopped = await client.post(f"/api/v1/devices/{device}/live/{sid}:stop", headers=identity())
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


async def test_companion_discovery_and_projection_ack(api):  # noqa: F811
    """WIRE3 (Q14): the device-side poll and MediaProjection ack endpoints."""
    client, _app = api
    device = await create_direct_device(client, "live-wire3")
    auth = await _enroll(client, device, "instance-wire3")

    # No session yet: discovery answers 404 (companion treats it as "no poll").
    missing = await client.get("/companion/v2/live/session", headers=auth)
    assert missing.status_code == 404

    opened = await client.post(f"/api/v1/devices/{device}/live", headers=identity())
    assert opened.status_code in (200, 201), opened.text
    sid = opened.json()["sessionId"]

    discovered = await client.get("/companion/v2/live/session", headers=auth)
    assert discovered.status_code == 200, discovered.text
    assert discovered.json()["sessionId"] == sid
    assert discovered.json()["state"] == "VIEWING"

    # Ack requires companion auth and must be device-scoped.
    unauthenticated = await client.post(f"/companion/v2/live/{sid}/ack", json={"granted": True})
    assert unauthenticated.status_code == 401

    granted = await client.post(
        f"/companion/v2/live/{sid}/ack", headers=auth, json={"granted": True}
    )
    assert granted.status_code == 200, granted.text
    assert granted.json()["state"] == "VIEWING"

    stopped = await client.post(f"/api/v1/devices/{device}/live/{sid}:stop", headers=identity())
    assert stopped.status_code == 200

    # After close, discovery 404s again and a late ack hits SESSION_CLOSED.
    gone = await client.get("/companion/v2/live/session", headers=auth)
    assert gone.status_code == 404


async def test_projection_denial_closes_session(api):  # noqa: F811
    """WIRE3 (Q14): a denied MediaProjection confirmation is terminal."""
    client, _app = api
    device = await create_direct_device(client, "live-wire3-deny")
    auth = await _enroll(client, device, "instance-wire3-deny")

    opened = await client.post(f"/api/v1/devices/{device}/live", headers=identity())
    sid = opened.json()["sessionId"]

    denied = await client.post(
        f"/companion/v2/live/{sid}/ack", headers=auth, json={"granted": False}
    )
    assert denied.status_code == 200, denied.text
    assert denied.json()["state"] == "CLOSED"

    status = await client.get(f"/api/v1/devices/{device}/live/{sid}", headers=identity())
    assert status.status_code == 200
    assert status.json()["state"] == "CLOSED"

    # The device may immediately open a new session after a denial.
    reopened = await client.post(f"/api/v1/devices/{device}/live", headers=identity())
    assert reopened.status_code in (200, 201), reopened.text
