"""A14 control-plane hotfix + identity D path tests (backend).

Contract anchors:
- control-plane/v1@20260917.1 §0 (control sync is never gated by local
  execution/queue/accessibility state), §2.1 (cursor pull + 410
  CURSOR_TOO_OLD), §2.2 (reconcile snapshot), §2.3 (heartbeat watermark /
  blocking task / inline events), §4 (CANCEL apply/ack: APPLIED converges,
  DEFERRED_RECONCILING stays RECONCILING), §5 (CONTROL_SEQ_INVALID/422).
- scope-decisions D-6/D-10: production identity D path — trust only the
  nginx-overwritten X-CloudCtl-Principal header, map it server-side to a
  provisioned user row, and reject every client self-reported identity
  header with 401; development behaviour is unchanged.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from cloudctl_api import create_app
from cloudctl_api.auth import current_actor
from cloudctl_api.db import (
    AuditEventRow,
    Database,
    DeviceLeaseRow,
    TenantRow,
    UserRow,
)
from cloudctl_api.settings import Settings
from cryptography.fernet import Fernet
from fastapi import FastAPI
from sqlalchemy import select
from starlette.requests import Request
from test_fleet_cancel_reconcile import (
    mint_probe_task,
    unknown_ledger_flow,
    view_task,
)
from test_platform_tasks import (
    OPERATOR,
    TENANT,
    _enroll,
    bind,
    create_account,
    create_direct_device,
    identity,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def api() -> AsyncIterator[tuple[httpx.AsyncClient, FastAPI]]:
    app = create_app(Settings(env="test", repository_mode="memory", dev_auth_bypass=True))
    await app.state.database.create_schema()
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, app


@pytest.fixture
async def principal_db() -> AsyncIterator[Database]:
    database = Database(Settings(env="test", repository_mode="memory"))
    await database.create_schema()
    now = datetime.now(UTC)
    async with database.unit_of_work() as session:
        session.add(TenantRow(id=TENANT, name="a14-principal-tenant", created_at=now))
        session.add(
            UserRow(
                id=OPERATOR,
                tenant_id=TENANT,
                oidc_subject="ldap:zhangsan",
                roles=["device_operator"],
                disabled=False,
                created_at=now,
            )
        )
        session.add(
            UserRow(
                id=str(uuid.uuid4()),
                tenant_id=TENANT,
                oidc_subject="ldap:disabled",
                roles=["device_operator"],
                disabled=True,
                created_at=now,
            )
        )
    yield database
    await database.dispose()


def production_settings() -> Settings:
    """A validator-passing production Settings (shapes only, nothing dials out)."""
    return Settings(
        env="production",
        repository_mode="postgresql",
        database_url="postgresql+asyncpg://cloudctl:cloudctl@127.0.0.1:5432/cloudctl",
        object_store_mode="s3",
        s3_access_key="test-access",
        s3_secret_key="test-secret",  # noqa: S106 - dummy value for shape validation
        oidc_issuer="https://oidc.example.invalid/",
        oidc_public_key_pem=(
            "-----BEGIN PUBLIC KEY-----\ndGVzdA==\n-----END PUBLIC KEY-----\n"
        ),
        wechat_secret_encryption_key=Fernet.generate_key().decode(),
    )


def auth_request(headers: dict[str, str], database: Any = None) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "query_string": b"",
        "headers": [
            (key.lower().encode(), value.encode()) for key, value in headers.items()
        ],
        "client": ("127.0.0.1", 42000),
        "app": SimpleNamespace(state=SimpleNamespace(database=database)),
        "state": {"request_id": "a14-auth-test"},
    }
    return Request(scope)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def running_cancel_requested_task(
    client: httpx.AsyncClient, name: str
) -> tuple[str, str, dict[str, str], str]:
    """Device + probe task driven to RUNNING, then operator cancel (desired)."""
    device = await create_direct_device(client, f"a14-{name}")
    account = await create_account(client, f"a14-{name}-acc")
    await bind(client, account, device)
    task_id = await mint_probe_task(client, device, account, f"a14-{name}-{uuid.uuid4()}")
    auth = await _enroll(client, device, f"a14-{name}-inst")
    claimed = await client.post(
        "/companion/v2/tasks/claim", headers=auth, json={"leaseSeconds": 60}
    )
    assert claimed.status_code == 200, claimed.text
    assert claimed.json()["taskId"] == task_id
    lease_id = str(claimed.json()["leaseId"])
    heartbeat = await client.post(
        f"/companion/v2/tasks/{task_id}/heartbeat",
        headers=auth,
        json={"leaseId": lease_id, "currentStep": 0, "leaseSeconds": 60},
    )
    assert heartbeat.status_code == 200, heartbeat.text
    cancelled = await client.post(
        f"/api/v1/platform-tasks/{task_id}:cancel",
        headers=identity(),
        json={"reason": "operator wants out"},
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["state"] == "CANCEL_REQUESTED"
    return task_id, device, auth, lease_id


async def device_beat(
    client: httpx.AsyncClient,
    auth: dict[str, str],
    *,
    last_applied: int | None = None,
    barrier: str | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "companionVersion": "1.0.0",
        "accessibilityEnabled": True,
        "runnerState": "RUNNING",
    }
    if last_applied is not None:
        body["lastAppliedControlSeq"] = last_applied
    if barrier is not None:
        body["safetyBarrier"] = barrier
    response = await client.post("/companion/v2/devices/heartbeat", headers=auth, json=body)
    assert response.status_code == 200, response.text
    return response.json()


async def control_pull(
    client: httpx.AsyncClient, auth: dict[str, str], after: int, limit: int | None = None
) -> httpx.Response:
    query = f"after={after}"
    if limit is not None:
        query += f"&limit={limit}"
    return await client.get(f"/companion/v2/control?{query}", headers=auth)


async def snapshot(
    client: httpx.AsyncClient, auth: dict[str, str]
) -> dict[str, Any]:
    response = await client.get("/companion/v2/reconcile-snapshot", headers=auth)
    assert response.status_code == 200, response.text
    return response.json()


async def ack(
    client: httpx.AsyncClient, auth: dict[str, str], body: dict[str, Any]
) -> httpx.Response:
    return await client.post("/companion/v2/control/ack", headers=auth, json=body)


async def audit_actions(app: FastAPI, task_id: str) -> list[str]:
    async with app.state.database.unit_of_work() as session:
        rows = list(
            await session.scalars(
                select(AuditEventRow).where(
                    AuditEventRow.resource_id == task_id,
                    AuditEventRow.action.like("platform.task.%"),
                )
            )
        )
    return sorted(row.action for row in rows)


async def device_lease_row(app: FastAPI, device: str) -> DeviceLeaseRow | None:
    async with app.state.database.unit_of_work() as session:
        return await session.get(DeviceLeaseRow, device)


# ---------------------------------------------------------------------------
# 1. §2.3 hotfix — heartbeat carries watermark / blocking task / inline events
# ---------------------------------------------------------------------------


async def test_heartbeat_carries_watermark_inline_events_and_blocking_task(api):
    client, _app = api
    task_id, device, auth, _lease = await running_cancel_requested_task(
        client, "hotfix-beat"
    )

    # Legacy client (no control fields): still 200, still carries the channel.
    beat = await device_beat(client, auth)
    assert beat["controlHighWatermark"] > 0
    assert len(beat["inlineEvents"]) == 1
    event = beat["inlineEvents"][0]
    assert event["taskId"] == task_id
    assert event["taskRevision"] == 1
    assert event["type"] == "CANCEL"  # §4: desired cancel on a live executor
    assert event["seq"] == beat["controlHighWatermark"]
    assert beat["blockingTask"] == {
        "taskId": task_id,
        "status": "CANCEL_REQUESTED",
        "taskRevision": 1,
    }

    # Applied cursor: nothing new pending → no inline events.
    caught_up = await device_beat(client, auth, last_applied=beat["controlHighWatermark"])
    assert caught_up["controlHighWatermark"] == beat["controlHighWatermark"]
    assert caught_up["inlineEvents"] == []
    assert caught_up["blockingTask"] == beat["blockingTask"]

    # A lagging client sees the missed events inline (≤2, newest-biased).
    lagging = await device_beat(client, auth, last_applied=0)
    assert lagging["inlineEvents"] == beat["inlineEvents"]

    # §2.3 request extension: the safety barrier is accepted transport state.
    barrier = await device_beat(client, auth, barrier="RECONCILING")
    assert barrier["ok"] is True
    listed = await client.get(
        "/api/v1/devices", headers=identity(role="security_admin")
    )
    assert listed.status_code == 200, listed.text
    record = next(item for item in listed.json() if item["id"] == device)
    assert record["capabilities"]["safetyBarrier"] == "RECONCILING"

    # A device with no tasks at all still gets the (empty) control channel.
    fresh_device = await create_direct_device(client, "a14-hotfix-empty")
    fresh_auth = await _enroll(client, fresh_device, "a14-hotfix-empty-inst")
    empty = await device_beat(client, fresh_auth, last_applied=0)
    assert empty["controlHighWatermark"] == 0
    assert empty["inlineEvents"] == []
    assert empty["blockingTask"] is None


# ---------------------------------------------------------------------------
# 2. §2.1 cursor pull + 410 CURSOR_TOO_OLD + §5 CONTROL_SEQ_INVALID
# ---------------------------------------------------------------------------


async def test_control_cursor_pull_pagination_and_cursor_too_old(api):
    client, _app = api
    task_one, device, auth, _lease = await running_cancel_requested_task(
        client, "cursor-one"
    )
    # A second task on the same device settles immediately (QUEUED cancel).
    account = await create_account(client, "a14-cursor-two-acc")
    await bind(client, account, device)
    task_two = await mint_probe_task(
        client, device, account, f"a14-cursor-two-{uuid.uuid4()}"
    )
    settled = await client.post(
        f"/api/v1/platform-tasks/{task_two}:cancel",
        headers=identity(),
        json={"reason": "parked, settle now"},
    )
    assert settled.status_code == 200, settled.text
    assert settled.json()["state"] == "CANCELLED"

    beat = await device_beat(client, auth)
    events = beat["inlineEvents"]
    assert len(events) == 2
    by_task = {event["taskId"]: event for event in events}
    assert by_task[task_one]["type"] == "CANCEL"  # deferred cancel (desired)
    assert by_task[task_two]["type"] == "TERMINAL"  # settled CANCELLED
    seqs = sorted(event["seq"] for event in events)
    assert len(set(seqs)) == 2  # unique per event, device-monotone
    floor, watermark = seqs[0], beat["controlHighWatermark"]
    assert watermark == seqs[1]

    # Cursor below the retention floor → 410 with snapshotRequired, never an
    # empty page pretending nothing changed (§2.1 negative fixture).
    stale = await control_pull(client, auth, 0)
    assert stale.status_code == 410, stale.text
    assert stale.json()["code"] == "CURSOR_TOO_OLD"
    assert stale.json()["snapshotRequired"] is True
    just_below = await control_pull(client, auth, floor - 1)
    assert just_below.status_code == 410

    # Catch-up from the floor: only the newer event remains.
    page = await control_pull(client, auth, floor)
    assert page.status_code == 200, page.text
    body = page.json()
    assert body["from"] == watermark
    assert body["through"] == watermark
    assert body["highWatermark"] == watermark
    assert [event["seq"] for event in body["events"]] == [watermark]
    assert body["events"][0]["taskId"] in {task_one, task_two}

    # At the watermark: empty page with a consistent window shape.
    caught_up = await control_pull(client, auth, watermark)
    assert caught_up.status_code == 200, caught_up.text
    assert caught_up.json() == {
        "from": watermark + 1,
        "through": watermark,
        "highWatermark": watermark,
        "events": [],
    }

    # limit is clamped to 1..50 and pages honor it.
    single = await control_pull(client, auth, floor, limit=1)
    assert single.status_code == 200
    assert len(single.json()["events"]) == 1
    too_many = await control_pull(client, auth, floor, limit=51)
    assert too_many.status_code == 422

    # §5: a malformed (negative) cursor is CONTROL_SEQ_INVALID/422.
    negative = await control_pull(client, auth, -1)
    assert negative.status_code == 422, negative.text
    assert negative.json()["code"] == "CONTROL_SEQ_INVALID"


async def test_control_cursor_all_events_compacted(api):
    """A device whose every event was pruned 410s instead of faking empty."""
    client, app = api
    task_id, device, auth, _lease = await running_cancel_requested_task(
        client, "compacted"
    )
    # Force the retention window empty: strip the steps header events.
    async with app.state.database.unit_of_work() as session:
        from cloudctl_api.db import MobileTaskRow

        row = await session.get(MobileTaskRow, task_id)
        assert row is not None
        header = dict((row.steps or [{}])[0] or {})
        header.pop("controlEvents", None)
        row.steps = [header, *(row.steps[1:] if row.steps else [])]
    gone = await control_pull(client, auth, 3)
    assert gone.status_code == 410, gone.text
    assert gone.json()["code"] == "CURSOR_TOO_OLD"
    assert gone.json()["snapshotRequired"] is True
    fresh = await control_pull(client, auth, 0)
    assert fresh.status_code == 200
    assert fresh.json()["highWatermark"] == 0


# ---------------------------------------------------------------------------
# 3. §2.2 reconcile snapshot — the convergence guarantee
# ---------------------------------------------------------------------------


async def test_reconcile_snapshot_converges_and_reports_ledger_blocks(api):
    client, app = api
    # Device one: one deferred-cancel task (RECONCILING) + one settled task.
    task_one, device, auth, _lease = await running_cancel_requested_task(
        client, "snap-one"
    )
    deferred = await ack(
        client,
        auth,
        {
            "taskId": task_one,
            "taskRevision": 1,
            "result": "CANCEL_DEFERRED_RECONCILING",
            "reason": "unknown outcome on screen",
        },
    )
    assert deferred.status_code == 200, deferred.text
    account = await create_account(client, "a14-snap-two-acc")
    await bind(client, account, device)
    task_two = await mint_probe_task(
        client, device, account, f"a14-snap-two-{uuid.uuid4()}"
    )
    settled = await client.post(
        f"/api/v1/platform-tasks/{task_two}:cancel",
        headers=identity(),
        json={"reason": "settle now"},
    )
    assert settled.status_code == 200, settled.text

    state = await snapshot(client, auth)
    assert state["controlHighWatermark"] > 0
    tasks = {item["taskId"]: item for item in state["tasks"]}
    assert tasks[task_one]["businessState"] == "RECONCILING"
    assert tasks[task_one]["terminal"] is False
    assert tasks[task_one]["ledgerBlocks"] is False  # no ledger rows involved
    assert tasks[task_two]["businessState"] == "CANCELLED"
    assert tasks[task_two]["terminal"] is True
    # The watermark agrees with the cursor channel.
    pull = await control_pull(client, auth, 0)
    assert pull.status_code == 410  # below floor → snapshot is the bootstrap

    # Device two: an open UNKNOWN action ledger row keeps blocking (§3.4) —
    # the ledger is decoupled from the task mirror state.
    unknown_task, unknown_device, unknown_auth, _lease = await unknown_ledger_flow(
        client, app, "a14-snap-unknown", status="UNKNOWN"
    )
    unknown_state = await snapshot(client, unknown_auth)
    unknown_tasks = {item["taskId"]: item for item in unknown_state["tasks"]}
    assert unknown_tasks[unknown_task]["ledgerBlocks"] is True
    assert unknown_tasks[unknown_task]["terminal"] is False


# ---------------------------------------------------------------------------
# 4. §4 cancel ack — APPLIED converges, DEFERRED stays RECONCILING
# ---------------------------------------------------------------------------


async def test_cancel_ack_applied_converges_and_releases_occupation(api):
    client, app = api
    task_id, device, auth, lease = await running_cancel_requested_task(
        client, "ack-applied"
    )
    lease_row = await device_lease_row(app, device)
    assert lease_row is not None and lease_row.canceled_at is None

    applied = await ack(
        client,
        auth,
        {"taskId": task_id, "taskRevision": 1, "result": "CANCEL_APPLIED"},
    )
    assert applied.status_code == 200, applied.text
    assert applied.json()["businessState"] == "CANCELLED"
    assert applied.json()["terminal"] is True
    assert applied.json()["result"] == "CANCEL_APPLIED"

    # Operator view: settled CANCELLED with the runner terminal spelling.
    view = await view_task(client, task_id)
    assert view["state"] == "CANCELLED"
    assert view["runnerStatus"] == "FAILED"
    assert [event["event"] for event in view["controlEvents"]] == [
        "CANCEL_REQUESTED",
        "CANCELLED",
    ]
    assert view["controlEvents"][-1]["actor"] == "companion"

    # The AUTO occupation is released with the ack, not lazily later.
    released = await device_lease_row(app, device)
    assert released is not None and released.canceled_at is not None
    assert "platform.task.cancel_acked" in await audit_actions(app, task_id)

    # The settled cancel shows up in the device control stream as TERMINAL.
    beat = await device_beat(client, auth)
    own = [event for event in beat["inlineEvents"] if event["taskId"] == task_id]
    assert [event["type"] for event in own] == ["CANCEL", "TERMINAL"]

    # Idempotent replay: retrying the same ack returns the same convergence.
    replay = await ack(
        client,
        auth,
        {"taskId": task_id, "taskRevision": 1, "result": "CANCEL_APPLIED"},
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["businessState"] == "CANCELLED"


async def test_cancel_ack_deferred_keeps_reconciling(api):
    client, app = api
    task_id, device, auth, lease = await running_cancel_requested_task(
        client, "ack-deferred"
    )

    deferred = await ack(
        client,
        auth,
        {
            "taskId": task_id,
            "taskRevision": 1,
            "result": "CANCEL_DEFERRED_RECONCILING",
            "reason": "irreversible submit already sent",
        },
    )
    assert deferred.status_code == 200, deferred.text
    assert deferred.json()["businessState"] == "RECONCILING"
    assert deferred.json()["terminal"] is False
    assert deferred.json()["result"] == "CANCEL_DEFERRED_RECONCILING"

    view = await view_task(client, task_id)
    assert view["state"] == "RECONCILING"
    assert view["stallReason"] == "irreversible submit already sent"
    assert "platform.task.cancel_deferred_reconciling" in await audit_actions(
        app, task_id
    )

    # The deferred branch is visible in the device control stream (§4 name).
    beat = await device_beat(client, auth)
    own = [event for event in beat["inlineEvents"] if event["taskId"] == task_id]
    assert [event["type"] for event in own] == ["CANCEL", "CANCEL_DEFERRED_RECONCILING"]

    # Idempotent replay keeps RECONCILING — never a hard terminal.
    replay = await ack(
        client,
        auth,
        {
            "taskId": task_id,
            "taskRevision": 1,
            "result": "CANCEL_DEFERRED_RECONCILING",
            "reason": "retry",
        },
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["businessState"] == "RECONCILING"
    assert replay.json()["terminal"] is False


async def test_cancel_ack_rejections(api):
    client, _app = api
    # No pending cancel: a plain RUNNING task cannot be acked.
    device = await create_direct_device(client, "a14-ack-run")
    account = await create_account(client, "a14-ack-run-acc")
    await bind(client, account, device)
    running = await mint_probe_task(
        client, device, account, f"a14-ack-run-{uuid.uuid4()}"
    )
    auth = await _enroll(client, device, "a14-ack-run-inst")
    claimed = await client.post(
        "/companion/v2/tasks/claim", headers=auth, json={"leaseSeconds": 60}
    )
    assert claimed.status_code == 200, claimed.text
    no_cancel = await ack(
        client, auth, {"taskId": running, "result": "CANCEL_APPLIED"}
    )
    assert no_cancel.status_code == 409, no_cancel.text

    # Stale taskRevision must not settle the task.
    task_id, device2, auth2, _lease = await running_cancel_requested_task(
        client, "ack-stale"
    )
    stale = await ack(
        client,
        auth2,
        {"taskId": task_id, "taskRevision": 99, "result": "CANCEL_APPLIED"},
    )
    assert stale.status_code == 409, stale.text
    assert (await view_task(client, task_id))["state"] == "CANCEL_REQUESTED"

    # Another device's binding cannot ack a foreign task.
    other_device = await create_direct_device(client, "a14-ack-other")
    other_auth = await _enroll(client, other_device, "a14-ack-other-inst")
    foreign = await client.post(
        "/companion/v2/control/ack",
        headers=other_auth,
        json={"taskId": task_id, "result": "CANCEL_APPLIED"},
    )
    assert foreign.status_code == 404, foreign.text

    # A settled non-cancel terminal refuses the ack too.
    settled = await client.post(
        f"/api/v1/platform-tasks/{running}:cancel",
        headers=identity(),
        json={"reason": "settle for ack test"},
    )
    assert settled.status_code == 200, settled.text
    assert settled.json()["state"] == "CANCELLED"
    wrong_state = await ack(
        client, auth, {"taskId": running, "result": "CANCEL_DEFERRED_RECONCILING"}
    )
    assert wrong_state.status_code == 409, wrong_state.text


# ---------------------------------------------------------------------------
# 5. §0 — control-plane sync is never gated by claim / ledger state
# ---------------------------------------------------------------------------


async def test_control_plane_not_gated_by_claim_blockers(api):
    client, app = api
    # Open UNKNOWN ledger rows block claim for the whole device…
    task_id, device, auth, _lease = await unknown_ledger_flow(
        client, app, "a14-never-gated", status="UNKNOWN"
    )
    waiting = await client.post(
        f"/api/v1/platform-tasks/{task_id}:reconcile",
        headers=identity(),
        json={
            "decision": "KEEP_WAITING",
            "evidence": "operator still verifying the listing",
        },
    )
    assert waiting.status_code == 200, waiting.text
    blocked = await client.post(
        "/companion/v2/tasks/claim", headers=auth, json={"leaseSeconds": 60}
    )
    assert blocked.status_code == 409, blocked.text

    # …but the control channels answer 200 regardless (§0: the incident).
    beat = await device_beat(client, auth, last_applied=0)
    assert beat["ok"] is True
    assert beat["controlHighWatermark"] > 0
    assert beat["blockingTask"]["taskId"] == task_id
    assert beat["blockingTask"]["status"] == "RECONCILING"
    state = await snapshot(client, auth)
    assert state["controlHighWatermark"] == beat["controlHighWatermark"]
    events = [
        event for event in beat["inlineEvents"] if event["taskId"] == task_id
    ]
    assert events, "the control events must ride the heartbeat channel"
    pull = await control_pull(client, auth, 0)
    assert pull.status_code == 410  # cursor below floor → snapshot bootstrap
    assert pull.json()["snapshotRequired"] is True


# ---------------------------------------------------------------------------
# 6. Identity D path (D-6/D-10) — production principal mapping
# ---------------------------------------------------------------------------


async def test_production_principal_maps_to_provisioned_user(principal_db):
    request = auth_request({"X-CloudCtl-Principal": "ldap:zhangsan"}, principal_db)
    actor = await current_actor(request, production_settings())
    assert str(actor.tenant_id) == TENANT
    assert str(actor.user_id) == OPERATOR
    assert "device_operator" in {str(role) for role in actor.roles}
    assert actor.mfa is True
    assert actor.request_id == "a14-auth-test"


async def test_production_rejects_self_reported_identity_headers(principal_db):
    settings = production_settings()
    forged = auth_request(
        {
            "X-CloudCtl-Principal": "ldap:zhangsan",
            "X-Roles": "security_admin",
            "X-Tenant-Id": TENANT,
        },
        principal_db,
    )
    with pytest.raises(Exception) as excinfo:
        await current_actor(forged, settings)
    assert getattr(excinfo.value, "status", None) == 401

    # The forged-header rejection applies to the bearer path as well.
    forged_bearer = auth_request({"X-User-Id": OPERATOR})
    with pytest.raises(Exception) as excinfo:
        await current_actor(forged_bearer, settings)
    assert getattr(excinfo.value, "status", None) == 401


async def test_production_unknown_or_disabled_principal_rejected(principal_db):
    settings = production_settings()
    unknown = auth_request({"X-CloudCtl-Principal": "ldap:nobody"}, principal_db)
    with pytest.raises(Exception) as excinfo:
        await current_actor(unknown, settings)
    assert getattr(excinfo.value, "status", None) == 401
    disabled = auth_request({"X-CloudCtl-Principal": "ldap:disabled"}, principal_db)
    with pytest.raises(Exception) as excinfo:
        await current_actor(disabled, settings)
    assert getattr(excinfo.value, "status", None) == 401
    # Absent any principal, the OIDC bearer path applies (verifier absent → 401).
    no_principal = auth_request({"Authorization": "Bearer garbage"}, principal_db)
    with pytest.raises(Exception) as excinfo:
        await current_actor(no_principal, settings)
    assert getattr(excinfo.value, "status", None) == 401


async def test_development_bypass_headers_still_accepted(api):
    """D-10: the development identity flow is unchanged by the D path."""
    client, _app = api
    listed = await client.get("/api/v1/mobile/tasks", headers=identity())
    assert listed.status_code == 200, listed.text
    denied = await client.get("/api/v1/mobile/tasks")
    assert denied.status_code == 401
