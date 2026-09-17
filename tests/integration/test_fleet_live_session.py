"""Fleet live tiered sessions (L10, live-capabilities/v1 K13) acceptance tests.

Covers the five acceptance groups from the L10 task card:

1. two sessions racing for REMOTE on one device -> exactly one wins (409),
   in-process and across two API instances sharing one database;
2. JPEG tier establishes with zero TURN config; WEBRTC tier without TURN is
   refused 503 (never silently downgraded);
3. cross-device session tokens and stale epochs are rejected;
4. VIEWING sessions cannot send input (K13 allowsInput derivation);
5. disconnect closes the session, reclaims the lease, and the old token is
   dead (410 LIVE_SESSION_TERMINAL on any further operation).
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from cloudctl_api import create_app
from cloudctl_api.db import DeviceLeaseRow, MobileTaskRow
from cloudctl_api.settings import Settings
from fastapi import FastAPI
from sqlalchemy import update
from test_p14_recipe_versions import (  # noqa: F401 - pytest fixture injection
    api,
    isolated_postgres,
    pg_url,
)
from test_platform_tasks import _enroll, create_direct_device, identity

TURN_ENV = {
    "CLOUDCTL_LIVE_TURN_ICE_SERVERS": (
        "turn:turn1.example.test:3478,turns:turn1.example.test:5349"
    ),
    "CLOUDCTL_LIVE_TURN_SHARED_SECRET": "integration-turn-secret-0123456789abcdef",
    "CLOUDCTL_LIVE_TURN_CREDENTIAL_TTL_SECONDS": "600",
    "CLOUDCTL_LIVE_TURN_TRANSPORT_POLICY": "relay",
    "CLOUDCTL_LIVE_TURN_CONNECTION_QUOTA": "3",
}


def live_headers(token: str | None = None, *, user: str | None = None) -> dict[str, str]:
    headers = identity()
    if user is not None:
        headers["X-User-Id"] = user
    if token:
        headers["X-Live-Session-Token"] = token
    return headers


OTHER_OPERATOR = "00000000-0000-7000-8000-000000000999"


class FakeCompanionSocket:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    async def send_json(self, message: dict[str, Any]) -> None:
        self.sent.append(message)


async def establish(
    client: httpx.AsyncClient,
    device: str,
    tier: str,
    *,
    transport: str | None = None,
    token: str | None = None,
    user: str | None = None,
) -> httpx.Response:
    body: dict[str, Any] = {"tier": tier}
    if transport is not None:
        body["transport"] = transport
    return await client.post(
        f"/api/v1/live/devices/{device}/sessions",
        headers=live_headers(token, user=user),
        json=body,
    )


async def ack(
    client: httpx.AsyncClient, companion_auth: dict[str, str], sid: str, granted: bool
) -> httpx.Response:
    return await client.post(
        f"/companion/v2/fleet-live/{sid}/ack",
        headers=companion_auth,
        json={"granted": granted},
    )


async def take_control(
    client: httpx.AsyncClient, sid: str, token: str | None
) -> httpx.Response:
    return await client.post(
        f"/api/v1/live/sessions/{sid}:take-control", headers=live_headers(token)
    )


async def send_input(
    client: httpx.AsyncClient,
    device: str,
    sid: str,
    token: str | None,
    **overrides: Any,
) -> httpx.Response:
    body: dict[str, Any] = {"kind": "tap", "seq": 1, "frameSeq": 1, "x": 10.0, "y": 20.0}
    body.update(overrides)
    return await client.post(
        f"/api/v1/live/devices/{device}/sessions/{sid}/input",
        headers=live_headers(token),
        json=body,
    )


async def create_mobile_task(
    client: httpx.AsyncClient, device: str, suffix: str
) -> str:
    response = await client.post(
        "/api/v1/mobile/tasks",
        headers={**identity(), "Idempotency-Key": f"fleet-live-{suffix}"},
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
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def fleet_service(app: FastAPI) -> Any:
    return app.state.fleet_live_service


async def remote_session(
    client: httpx.AsyncClient,
    app: FastAPI,
    device: str,
    *,
    tier: str = "INTERACTIVE_REMOTE",
) -> tuple[str, str, dict[str, str]]:
    """establish + companion ack + take-control; returns (sid, token, auth)."""
    opened = await establish(client, device, tier)
    assert opened.status_code == 201, opened.text
    sid = opened.json()["sessionId"]
    token = opened.json()["sessionToken"]
    auth = await _enroll(client, device, f"instance-{sid[:8]}")
    acknowledged = await ack(client, auth, sid, granted=True)
    assert acknowledged.status_code == 200, acknowledged.text
    assert acknowledged.json()["authorization"]["userConfirmedAt"] is not None
    controlled = await take_control(client, sid, token)
    assert controlled.status_code == 200, controlled.text
    assert controlled.json()["state"] == "REMOTE"
    return sid, token, auth


@pytest.fixture
async def api_no_turn(monkeypatch) -> AsyncIterator[tuple[httpx.AsyncClient, FastAPI]]:
    for key in TURN_ENV:
        monkeypatch.delenv(key, raising=False)
    app = create_app(Settings(env="test", repository_mode="memory", dev_auth_bypass=True))
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, app


@pytest.fixture
async def api_turn(monkeypatch) -> AsyncIterator[tuple[httpx.AsyncClient, FastAPI]]:
    for key, value in TURN_ENV.items():
        monkeypatch.setenv(key, value)
    app = create_app(Settings(env="test", repository_mode="memory", dev_auth_bypass=True))
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, app


@pytest.fixture
async def twin_apps(pg_url) -> AsyncIterator[list[tuple[httpx.AsyncClient, FastAPI]]]:  # noqa: F811
    """Two independent API instances over one Postgres: cross-process proof."""
    instances: list[tuple[httpx.AsyncClient, FastAPI]] = []
    contexts = []
    for _ in range(2):
        settings = Settings(
            env="test",
            repository_mode="postgresql",
            database_url=pg_url,
            dev_auth_bypass=True,
        )
        app = create_app(settings)
        # PostgreSQL mode does not auto-create schema in lifespan.
        await app.state.database.create_schema()
        context = app.router.lifespan_context(app)
        await context.__aenter__()
        contexts.append(context)
        transport = httpx.ASGITransport(app=app)
        client = httpx.AsyncClient(transport=transport, base_url="http://test")
        instances.append((client, app))
    try:
        yield instances
    finally:
        for client, _app in instances:
            await client.aclose()
        for context in contexts:
            await context.__aexit__(None, None, None)


# ---------------------------------------------------------------------------
# Acceptance group 2: explicit transport selection, JPEG needs no TURN
# ---------------------------------------------------------------------------


async def test_jpeg_preview_establishes_without_turn_and_stays_read_only(
    api_no_turn,
) -> None:
    client, app = api_no_turn
    device = await create_direct_device(client, "fl-jpeg-dev")

    opened = await establish(client, device, "JPEG_PREVIEW")
    assert opened.status_code == 201, opened.text
    session = opened.json()
    assert session["state"] == "VIEWING"
    assert session["tier"] == "JPEG_PREVIEW"
    assert session["transport"] == "JPEG_WS"
    assert session["capabilities"] == {
        "allowsInput": False,
        "uiLabel": "preview",
        "frameDownlink": True,
        "turnRequired": False,
    }
    assert session["lease"]["purpose"] == "LIVE"
    assert session["lease"]["epoch"] >= 1
    assert session["maxDurationMinutes"] == 30
    assert session["gates"] == [
        "GATE_LIVE_LEASE",
        "GATE_MEDIAPROJECTION_AUTH",
        "GATE_JPEG_TRANSPORT",
    ]
    assert session["transportPlan"]["kind"] == "JPEG_WS"
    assert session["transportPlan"]["turnRequired"] is False
    assert session["authorization"]["mediaProjectionRequired"] is True
    assert session["authorization"]["persistsAcrossReboot"] is False
    assert session["authorization"]["userConfirmedAt"] is None
    assert session["sessionToken"]

    sid = session["sessionId"]
    token = session["sessionToken"]

    # Group 4: VIEWING + read-only tier rejects any input with 403.
    forbidden = await send_input(client, device, sid, token, seq=1, frameSeq=1)
    assert forbidden.status_code == 403, forbidden.text
    assert forbidden.json()["code"] == "LIVE_INPUT_FORBIDDEN"

    # Read-only tier cannot take control either.
    controlled = await take_control(client, sid, token)
    assert controlled.status_code == 403
    assert controlled.json()["code"] == "LIVE_INPUT_FORBIDDEN"

    # Duplicate live session on the device conflicts.
    duplicate = await establish(client, device, "JPEG_PREVIEW")
    assert duplicate.status_code == 409
    assert "LIVE_SESSION_EXISTS" in duplicate.text


async def test_webrtc_without_turn_is_refused_not_downgraded(api_no_turn) -> None:
    client, app = api_no_turn
    device = await create_direct_device(client, "fl-noturn-dev")

    refused = await establish(client, device, "WEBRTC")
    assert refused.status_code == 503, refused.text
    assert refused.json()["code"] == "LIVE_TURN_UNAVAILABLE"
    # Refusal, not downgrade: no session was created on any transport.
    assert fleet_service(app).sessions == {}


async def test_webrtc_with_turn_establishes_with_credentials(api_turn) -> None:
    client, _ = api_turn
    device = await create_direct_device(client, "fl-turn-dev")

    opened = await establish(client, device, "WEBRTC")
    assert opened.status_code == 201, opened.text
    session = opened.json()
    assert session["transport"] == "WEBRTC"
    assert session["capabilities"]["turnRequired"] is True
    assert session["capabilities"]["uiLabel"] == "interactive-hd"
    assert "GATE_TURN_DEPLOY" in session["gates"]
    assert "GATE_JPEG_TRANSPORT" not in session["gates"]
    plan = session["transportPlan"]
    assert plan["kind"] == "WEBRTC"
    (ice,) = plan["details"]["iceServers"]
    assert ice["username"] and ice["credential"]
    assert plan["details"]["credentialTtlSeconds"] == 600
    assert plan["details"]["connectionQuota"] == 3


async def test_tier_transport_combinations_outside_closed_set_rejected(api) -> None:  # noqa: F811
    client, _ = api
    device = await create_direct_device(client, "fl-closed-set")
    for tier, transport in (
        ("WEBRTC", "JPEG_WS"),
        ("JPEG_PREVIEW", "WEBRTC"),
        ("INTERACTIVE_REMOTE", "WEBRTC"),
        ("NO_SUCH_TIER", None),
    ):
        response = await establish(client, device, tier, transport=transport)
        assert response.status_code == 422, (tier, transport, response.text)
        assert response.json()["code"] == "LIVE_TIER_UNSUPPORTED"


# ---------------------------------------------------------------------------
# MediaProjection authorization (K13 §6)
# ---------------------------------------------------------------------------


async def test_take_control_requires_projection_ack(api) -> None:  # noqa: F811
    client, _ = api
    device = await create_direct_device(client, "fl-ack-dev")
    opened = await establish(client, device, "INTERACTIVE_REMOTE")
    assert opened.status_code == 201, opened.text
    sid = opened.json()["sessionId"]
    token = opened.json()["sessionToken"]

    refused = await take_control(client, sid, token)
    assert refused.status_code == 428, refused.text
    assert refused.json()["code"] == "LIVE_AUTH_REQUIRED"

    # Ack must come from the device's own companion binding.
    other_device = await create_direct_device(client, "fl-ack-other")
    other_auth = await _enroll(client, other_device, "fl-ack-other-inst")
    wrong_device = await ack(client, other_auth, sid, granted=True)
    assert wrong_device.status_code == 404

    auth = await _enroll(client, device, "fl-ack-inst")
    acknowledged = await ack(client, auth, sid, granted=True)
    assert acknowledged.status_code == 200, acknowledged.text
    assert acknowledged.json()["authorization"]["userConfirmedAt"] is not None

    controlled = await take_control(client, sid, token)
    assert controlled.status_code == 200, controlled.text
    assert controlled.json()["state"] == "REMOTE"


async def test_ack_denied_closes_session_as_terminal(api) -> None:  # noqa: F811
    client, _ = api
    device = await create_direct_device(client, "fl-ack-deny")
    opened = await establish(client, device, "JPEG_PREVIEW")
    sid = opened.json()["sessionId"]
    token = opened.json()["sessionToken"]

    auth = await _enroll(client, device, "fl-ack-deny-inst")
    denied = await ack(client, auth, sid, granted=False)
    assert denied.status_code == 200, denied.text
    assert denied.json()["state"] == "CLOSED"
    assert denied.json()["terminal"]["cause"] == "PROJECTION_REVOKED"
    assert denied.json()["terminal"]["tokenInvalidated"] is True

    later = await take_control(client, sid, token)
    assert later.status_code == 410
    assert later.json()["code"] == "LIVE_SESSION_TERMINAL"


# ---------------------------------------------------------------------------
# Acceptance group 1: single writer via the DB lease row
# ---------------------------------------------------------------------------


async def test_remote_write_lease_single_writer_same_process(api) -> None:  # noqa: F811
    client, app = api
    device = await create_direct_device(client, "fl-single-writer")
    auth = await _enroll(client, device, "fl-single-inst")

    # Session 1 stays VIEWING (read-only marker row, nothing blocked).
    opened1 = await establish(client, device, "INTERACTIVE_REMOTE")
    assert opened1.status_code == 201, opened1.text
    sid1 = opened1.json()["sessionId"]
    token1 = opened1.json()["sessionToken"]
    acknowledged1 = await ack(client, auth, sid1, granted=True)
    assert acknowledged1.status_code == 200, acknowledged1.text

    # An AUTO claim may take the lane while VIEWING (VIEWING blocks nothing);
    # that is what lets a second session legitimately come into existence.
    task1 = await create_mobile_task(client, device, "sw-1")
    claimed = await client.post(
        "/companion/v2/tasks/claim", headers=auth, json={"leaseSeconds": 60}
    )
    assert claimed.status_code == 200, claimed.text
    lease1 = claimed.json()["leaseId"]

    opened2 = await establish(client, device, "INTERACTIVE_REMOTE")
    assert opened2.status_code == 201, opened2.text
    sid2 = opened2.json()["sessionId"]
    token2 = opened2.json()["sessionToken"]

    acknowledged2 = await ack(client, auth, sid2, granted=True)
    assert acknowledged2.status_code == 200, acknowledged2.text
    controlled2 = await take_control(client, sid2, token2)
    assert controlled2.status_code == 200, controlled2.text
    assert controlled2.json()["state"] == "REMOTE"
    remote_epoch = controlled2.json()["lease"]["epoch"]

    # First session loses the race for the write lease.
    controlled1 = await take_control(client, sid1, token1)
    assert controlled1.status_code == 409, controlled1.text
    assert "LIVE_REMOTE_HELD" in controlled1.text

    # The DB row (not any in-process flag) is what arbitrates claims now.
    async with app.state.database.unit_of_work() as db:
        row = await db.get(DeviceLeaseRow, device)
        assert row is not None
        assert row.owner_type == "REMOTE"
        assert row.owner_workflow_id == f"live/{sid2}"
        assert row.fencing_token == remote_epoch

    completed = await client.post(
        f"/companion/v2/tasks/{task1}/complete",
        headers=auth,
        json={"leaseId": lease1, "result": {}},
    )
    assert completed.status_code == 200, completed.text

    # Single writer: claim is refused while the REMOTE lease is active.
    await create_mobile_task(client, device, "sw-2")
    refused = await client.post(
        "/companion/v2/tasks/claim", headers=auth, json={"leaseSeconds": 60}
    )
    assert refused.status_code == 409, refused.text
    assert "device write lease is held by remote control" in refused.text

    released = await client.post(
        f"/api/v1/live/sessions/{sid2}:release", headers=live_headers(token2)
    )
    assert released.status_code == 200, released.text
    assert released.json()["state"] == "VIEWING"
    assert released.json()["handover"]["singleWriterRestored"] is True

    # Handover restores queue eligibility: claim works again through the row.
    async with app.state.database.unit_of_work() as db:
        row = await db.get(DeviceLeaseRow, device)
        assert row is not None
        assert row.owner_type == "LIVE"
    reclaimed = await client.post(
        "/companion/v2/tasks/claim", headers=auth, json={"leaseSeconds": 60}
    )
    assert reclaimed.status_code == 200, reclaimed.text
    assert reclaimed.json()["taskId"]


async def test_cross_process_remote_contention_resolved_by_db_row(twin_apps) -> None:
    (client1, _app1), (client2, _app2) = twin_apps
    device = await create_direct_device(client1, "fl-cross-dev")

    # Session 1 on process 1, VIEWING only (marker row in shared Postgres).
    opened1 = await establish(client1, device, "INTERACTIVE_REMOTE")
    assert opened1.status_code == 201, opened1.text
    sid1 = opened1.json()["sessionId"]
    token1 = opened1.json()["sessionToken"]
    auth = await _enroll(client1, device, "fl-cross-inst")
    acknowledged1 = await ack(client1, auth, sid1, granted=True)
    assert acknowledged1.status_code == 200, acknowledged1.text

    # Process 2 sees process 1's session marker through the shared database.
    blocked = await establish(client2, device, "INTERACTIVE_REMOTE")
    assert blocked.status_code == 409
    assert "LIVE_SESSION_EXISTS" in blocked.text

    # AUTO claim (from the other process) frees the lane while VIEWING.
    task1 = await create_mobile_task(client1, device, "x-1")
    claimed = await client2.post(
        "/companion/v2/tasks/claim", headers=auth, json={"leaseSeconds": 60}
    )
    assert claimed.status_code == 200, claimed.text
    completed = await client2.post(
        f"/companion/v2/tasks/{task1}/complete",
        headers=auth,
        json={"leaseId": claimed.json()["leaseId"], "result": {}},
    )
    assert completed.status_code == 200, completed.text

    # Process 2 establishes and takes the write lease (fresh companion
    # binding; re-enrolling revokes the previous binding token).
    sid2, token2, auth2 = await remote_session(client2, _app2, device)

    # Process 1's session cannot steal the write lease held by process 2.
    stolen = await take_control(client1, sid1, token1)
    assert stolen.status_code == 409, stolen.text
    assert "LIVE_REMOTE_HELD" in stolen.text

    # And the claiming path in process 1 respects process 2's REMOTE row.
    await create_mobile_task(client1, device, "x-2")
    refused = await client1.post(
        "/companion/v2/tasks/claim", headers=auth2, json={"leaseSeconds": 60}
    )
    assert refused.status_code == 409, refused.text
    assert "device write lease is held by remote control" in refused.text


# ---------------------------------------------------------------------------
# Acceptance group 3: four-tuple binding, tokens, epochs
# ---------------------------------------------------------------------------


async def test_cross_device_token_and_stale_epoch_rejected(api) -> None:  # noqa: F811
    client, app = api
    device = await create_direct_device(client, "fl-binding-dev")
    other_device = await create_direct_device(client, "fl-binding-other")

    opened = await establish(client, device, "INTERACTIVE_REMOTE")
    sid = opened.json()["sessionId"]
    token = opened.json()["sessionToken"]
    establish_epoch = opened.json()["lease"]["epoch"]
    auth = await _enroll(client, device, "fl-binding-inst")
    acknowledged = await ack(client, auth, sid, granted=True)
    assert acknowledged.status_code == 200
    controlled = await take_control(client, sid, token)
    assert controlled.status_code == 200
    remote_epoch = controlled.json()["lease"]["epoch"]
    assert remote_epoch > establish_epoch

    fleet_service(app).attach_companion(sid, FakeCompanionSocket())
    fleet_service(app).note_frame(sid, 100)

    # Session token bound to its device: another device's route rejects it.
    cross_device = await send_input(
        client, other_device, sid, token, seq=1, frameSeq=100, epoch=remote_epoch
    )
    assert cross_device.status_code == 404, cross_device.text

    # Old epoch from before the remote grant is refused outright.
    stale_epoch = await send_input(
        client, device, sid, token, seq=1, frameSeq=100, epoch=establish_epoch
    )
    assert stale_epoch.status_code == 409, stale_epoch.text
    assert "LIVE_EPOCH_STALE" in stale_epoch.text

    # Four-tuple: another operator cannot use the session token.
    stranger = await client.get(
        f"/api/v1/live/sessions/{sid}", headers=live_headers(token, user=OTHER_OPERATOR)
    )
    assert stranger.status_code == 404

    # Wrong token is an authentication failure.
    bad_token = await client.get(
        f"/api/v1/live/sessions/{sid}", headers=live_headers("not-the-token")
    )
    assert bad_token.status_code == 401

    # The happy path still works: accepted input reaches the companion.
    accepted = await send_input(
        client, device, sid, token, seq=1, frameSeq=100, epoch=remote_epoch
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json() == {
        "accepted": True,
        "inputWatermark": 1,
        "latestFrameSeq": 100,
    }


# ---------------------------------------------------------------------------
# Acceptance group 4 (input policy details, K13 §4)
# ---------------------------------------------------------------------------


async def test_input_watermark_regression_expiry_and_rate_rules(api) -> None:  # noqa: F811
    client, app = api
    device = await create_direct_device(client, "fl-input-dev")
    sid, token, _ = await remote_session(client, app, device)

    companion = FakeCompanionSocket()
    fleet_service(app).attach_companion(sid, companion)
    fleet_service(app).note_frame(sid, 100)

    accepted = await send_input(client, device, sid, token, seq=1, frameSeq=100)
    assert accepted.status_code == 200, accepted.text

    # seq regression: rejected, session keeps REMOTE at first.
    replay = await send_input(client, device, sid, token, seq=1, frameSeq=100)
    assert replay.status_code == 422
    assert replay.json()["code"] == "INPUT_SEQ_REGRESSION"
    assert replay.json()["fields"]["inputWatermark"] == "1"

    status = await client.get(
        f"/api/v1/live/sessions/{sid}", headers=live_headers(token)
    )
    assert status.json()["state"] == "REMOTE"

    # Repeated regressions in a short window sever the REMOTE grant.
    for _ in range(2):
        await send_input(client, device, sid, token, seq=1, frameSeq=100)
    status = await client.get(
        f"/api/v1/live/sessions/{sid}", headers=live_headers(token)
    )
    assert status.json()["state"] == "VIEWING"

    # Fresh grant with a new epoch; frame watermark rules next.
    controlled = await take_control(client, sid, token)
    assert controlled.status_code == 200
    epoch = controlled.json()["lease"]["epoch"]

    fleet_service(app).note_frame(sid, 105)
    # Stale frame threshold (default 10): latest 111 vs frameSeq 100.
    fleet_service(app).note_frame(sid, 111)
    stale = await send_input(client, device, sid, token, seq=2, frameSeq=100, epoch=epoch)
    assert stale.status_code == 422
    assert stale.json()["code"] == "INPUT_EXPIRED"

    # Gesture TTL: frame 105 delivered, but long ago.
    live = fleet_service(app).sessions[sid]
    live.frame_delivered_at[105] = time.monotonic() - 3.0
    expired = await send_input(client, device, sid, token, seq=3, frameSeq=105, epoch=epoch)
    assert expired.status_code == 422
    assert expired.json()["code"] == "INPUT_EXPIRED"

    # Rate limit: >10 accepted inputs per second severs REMOTE. The window is
    # pre-loaded with 10 fresh stamps so the boundary is deterministic.
    fleet_service(app).note_frame(sid, 120)
    live = fleet_service(app).sessions[sid]
    live.input_times = [time.monotonic() - 0.05] * 10
    flooded = await send_input(
        client, device, sid, token, seq=30, frameSeq=120, epoch=epoch
    )
    assert flooded.status_code == 429, flooded.text
    assert flooded.json()["code"] == "LIVE_RATE_LIMITED"
    status = await client.get(
        f"/api/v1/live/sessions/{sid}", headers=live_headers(token)
    )
    assert status.json()["state"] == "VIEWING"

    # Input metadata was audited (rejections included), frames never stored.
    from cloudctl_api.db import AuditEventRow
    from sqlalchemy import select

    async with app.state.database.unit_of_work() as db:
        actions = list(
            await db.scalars(
                select(AuditEventRow.action).where(AuditEventRow.resource_id == sid)
            )
        )
    assert "live.session.established" in actions
    assert "live.session.tier.granted" in actions
    assert "live.session.take-control" in actions
    assert "live.session.release" in actions


async def test_release_handover_reports_affected_tasks(api) -> None:  # noqa: F811
    client, app = api
    device = await create_direct_device(client, "fl-handover-dev")
    task_id = await create_mobile_task(client, device, "hv-1")
    auth = await _enroll(client, device, "fl-handover-inst")

    opened = await establish(client, device, "INTERACTIVE_REMOTE")
    assert opened.status_code == 201, opened.text
    sid = opened.json()["sessionId"]
    token = opened.json()["sessionToken"]
    acknowledged = await ack(client, auth, sid, granted=True)
    assert acknowledged.status_code == 200, acknowledged.text

    # A running task exists when control is taken.
    async with app.state.database.unit_of_work() as db:
        await db.execute(
            update(MobileTaskRow)
            .where(MobileTaskRow.id == task_id)
            .values(business_state="RUNNING")
        )

    controlled = await take_control(client, sid, token)
    assert controlled.status_code == 200, controlled.text
    async with app.state.database.unit_of_work() as db:
        task = await db.get(MobileTaskRow, task_id)
        assert task is not None
        assert task.business_state == "PAUSED_WAITING_USER"
        assert task.stall_reason == "live remote control"

    released = await client.post(
        f"/api/v1/live/sessions/{sid}:release", headers=live_headers(token)
    )
    assert released.status_code == 200, released.text
    handover = released.json()["handover"]
    assert handover["from"] == "REMOTE"
    assert handover["to"] == "VIEWING"
    assert handover["singleWriterRestored"] is True
    assert handover["frameDownlinkContinues"] is True
    (affected,) = handover["affectedTasks"]
    assert affected["taskId"] == task_id
    assert affected["pauseState"] == "PAUSED_WAITING_USER"
    assert affected["resumeMode"] == "REQUEUE_AUTO"

    # Queue eligibility restored: claim no longer hits the write lease; the
    # paused task stays blocking (204, nothing claimable) until resumed.
    eligible = await client.post(
        "/companion/v2/tasks/claim", headers=auth, json={"leaseSeconds": 60}
    )
    assert eligible.status_code == 204, eligible.text


# ---------------------------------------------------------------------------
# Acceptance group 5: disconnect reclamation and token invalidation
# ---------------------------------------------------------------------------


async def test_disconnect_closes_session_reclaims_lease_and_kills_token(api) -> None:  # noqa: F811
    client, app = api
    device = await create_direct_device(client, "fl-disconnect-dev")
    sid, token, _ = await remote_session(client, app, device)

    async with app.state.database.unit_of_work() as db:
        row = await db.get(DeviceLeaseRow, device)
        assert row is not None
        assert row.owner_type == "REMOTE"

    disconnected = await client.post(
        f"/api/v1/live/sessions/{sid}/disconnect",
        headers=live_headers(token),
        json={"who": "operator"},
    )
    assert disconnected.status_code == 200, disconnected.text
    # Abnormal handover first: REMOTE grant dropped, writer lane restored.
    assert disconnected.json()["state"] == "VIEWING"
    async with app.state.database.unit_of_work() as db:
        row = await db.get(DeviceLeaseRow, device)
        assert row is not None
        assert row.owner_type == "LIVE"

    # Grace window expires without a re-attach -> terminal.
    live = fleet_service(app).sessions[sid]
    assert live.operator_lost_monotonic is not None
    live.operator_lost_monotonic -= 11.0
    status = await client.get(
        f"/api/v1/live/sessions/{sid}", headers=live_headers(token)
    )
    assert status.status_code == 200
    body = status.json()
    assert body["state"] == "CLOSED"
    assert body["terminal"]["cause"] == "DISCONNECT_GRACE_EXPIRED"
    assert body["terminal"]["resumable"] is False
    assert body["terminal"]["reauthorizationRequired"] is True
    assert body["terminal"]["tokenInvalidated"] is True

    # Lease row is reclaimed.
    async with app.state.database.unit_of_work() as db:
        row = await db.get(DeviceLeaseRow, device)
        assert row is not None
        assert row.canceled_at is not None

    # Old token is dead for every further operation.
    stopped = await client.post(
        f"/api/v1/live/sessions/{sid}:stop", headers=live_headers(token)
    )
    assert stopped.status_code == 410
    assert stopped.json()["code"] == "LIVE_SESSION_TERMINAL"
    injected = await send_input(client, device, sid, token, seq=1, frameSeq=1)
    assert injected.status_code == 410
    assert injected.json()["code"] == "LIVE_SESSION_TERMINAL"

    # ...but a brand-new session on the device is possible again.
    reopened = await establish(client, device, "JPEG_PREVIEW")
    assert reopened.status_code == 201, reopened.text
