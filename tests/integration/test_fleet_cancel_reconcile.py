"""A12 cancel / manual-wait / uncertain-result convergence tests (backend).

Contract anchors:
- task-schedule/v1@20260916.1 §4 (pause→PAUSE_REQUESTED→ack-paused→
  PAUSED_WAITING_USER; cancel terminal-idempotent; RECONCILING→409 first
  reconcile; double-L CANCELLED spelling),
- fleet-identity/v1@20260916.1 §5/§8 (four-state mapping; UNKNOWN not erased
  by cancel; open-UNKNOWN blocks reclaim with 409 RECONCILE_REQUIRED).

Covers the four implementation bullets of the A12 task card:
1. the explicit control-transition matrix — legal cancel/pause/ack ordering
   under queued/preflight/running/paused/commit-intent/unknown, asserted
   total-and-closed in code and executed state-by-state through the API here;
2. persisted control events with a per-task monotonic revision, cancel
   releasing the device-lease occupation, duplicate + out-of-order events
   idempotent or refused;
3. KEEP_WAITING preserving open UNKNOWN ledger rows; closure only with
   trusted evidence + permission + audit (APPLIED vs NOT_SUBMITTED conflict);
4. the read-only window proof: old executor stopped AND occupancy free —
   never clearing UNKNOWN, never unlocking the device globally.

The functional coverage runs on the in-memory SQLite app; one cross-device
non-blocking proof runs on a disposable PostgreSQL cluster because that is
the engine the row-lock guarantees are stated for.
"""

from __future__ import annotations

import shutil
import socket
import subprocess
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from cloudctl_api import create_app
from cloudctl_api.db import (
    AuditEventRow,
    DeviceLeaseRow,
    MobileActionCommitRow,
    MobileTaskRow,
)
from cloudctl_api.mobile_actions import steps_action_identity
from cloudctl_api.platform_tasks import (
    ACK_PAUSED_OUTCOMES,
    ACK_PAUSED_TRANSITIONS,
    BUSINESS_STATES,
    CANCEL_OUTCOMES,
    CANCEL_TRANSITIONS,
    PAUSE_OUTCOMES,
    PAUSE_TRANSITIONS,
    RESUME_OUTCOMES,
    RESUME_TRANSITIONS,
    evaluate_readonly_window,
)
from cloudctl_api.settings import Settings
from fastapi import FastAPI
from sqlalchemy import select
from test_platform_tasks import (
    PROBE,
    TENANT,
    _enroll,
    bind,
    create_account,
    create_direct_device,
    identity,
)
from test_xianyu_maintenance import _create_steps_task, delist_steps

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


@pytest.fixture(scope="module")
def isolated_postgres(tmp_path_factory):
    """Never use DATABASE_URL: start our own disposable cluster on a free port."""
    if not all(shutil.which(tool) for tool in ("initdb", "pg_ctl", "createdb")):
        pytest.skip("local PostgreSQL binaries unavailable")
    root = tmp_path_factory.mktemp("a12-postgres")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    subprocess.run(  # noqa: S603 - fixed PostgreSQL tools and test-owned paths
        ["initdb", "-D", str(root / "data"), "-A", "trust", "-U", "a12test"],  # noqa: S607
        check=True,
        capture_output=True,
    )
    subprocess.run(  # noqa: S603 - fixed PostgreSQL tools and test-owned paths
        [  # noqa: S607
            "pg_ctl",
            "-D",
            str(root / "data"),
            "-l",
            str(root / "server.log"),
            "-o",
            f"-h 127.0.0.1 -p {port} -c unix_socket_directories=''",
            "-w",
            "start",
        ],
        check=True,
        capture_output=True,
    )
    try:
        yield port
    finally:
        subprocess.run(  # noqa: S603 - fixed PostgreSQL tools and test-owned paths
            ["pg_ctl", "-D", str(root / "data"), "-m", "immediate", "-w", "stop"],  # noqa: S607
            check=True,
            capture_output=True,
        )


@pytest.fixture
def pg_url(isolated_postgres):
    name = "a12_" + uuid.uuid4().hex
    subprocess.run(  # noqa: S603 - fixed PostgreSQL tools and test-owned paths
        ["createdb", "-h", "127.0.0.1", "-p", str(isolated_postgres), "-U", "a12test", name],  # noqa: S607
        check=True,
        capture_output=True,
    )
    return f"postgresql+asyncpg://a12test@127.0.0.1:{isolated_postgres}/{name}"


@asynccontextmanager
async def api_process(pg_url: str) -> AsyncIterator[tuple[httpx.AsyncClient, FastAPI]]:
    """One independent API process (own engine/connection pool) on the cluster."""
    app = create_app(
        Settings(
            env="test",
            repository_mode="postgresql",
            database_url=pg_url,
            dev_auth_bypass=True,
        )
    )
    await app.state.database.create_schema()
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def mint_probe_task(
    client: httpx.AsyncClient, device: str, account: str, key: str
) -> str:
    created = await client.post(
        "/api/v1/platform-tasks",
        headers={**identity(), "Idempotency-Key": key},
        json={"deviceId": device, "accountId": account, **PROBE},
    )
    assert created.status_code == 201, created.text
    return str(created.json()["items"][0]["taskId"])


async def view_task(client: httpx.AsyncClient, task_id: str) -> dict[str, Any]:
    response = await client.get(f"/api/v1/platform-tasks/{task_id}", headers=identity())
    assert response.status_code == 200, response.text
    return response.json()


async def control(
    client: httpx.AsyncClient, task_id: str, action: str, body: dict[str, Any]
) -> httpx.Response:
    return await client.post(
        f"/api/v1/platform-tasks/{task_id}:{action}",
        headers=identity(),
        json=body,
    )


async def patch_task(
    app: FastAPI, task_id: str, mutate: Callable[[MobileTaskRow], None]
) -> None:
    async with app.state.database.unit_of_work() as session:
        row = await session.get(MobileTaskRow, task_id)
        assert row is not None
        mutate(row)


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


CLAIMED_STATES = {
    "PREFLIGHT",
    "RUNNING",
    "PAUSE_REQUESTED",
    "PAUSED_WAITING_USER",
    "RESUME_CHECK",
    "CANCEL_REQUESTED",
}


async def task_in_state(
    client: httpx.AsyncClient, app: FastAPI, *, state: str, name: str
) -> tuple[str, str, dict[str, str], str | None]:
    """Fresh device + account + probe task driven into ``state``.

    Real API transitions are preferred; only the states no API path reaches
    (WAITING_MATERIALS and the non-CANCELLED terminals) are staged by patch.
    """
    device = await create_direct_device(client, f"a12-{name}")
    account = await create_account(client, f"a12-{name}-acc")
    await bind(client, account, device)
    task_id = await mint_probe_task(client, device, account, f"a12-{name}-{uuid.uuid4()}")
    lease_id: str | None = None
    if state == "QUEUED":
        pass  # freshly minted task already sits in QUEUED
    elif state == "CANCELLED":
        response = await control(client, task_id, "cancel", {"reason": "settle now"})
        assert response.status_code == 200, response.text
    elif state == "RECONCILING":
        response = await control(
            client, task_id, "mark-unknown", {"reason": "uncertain result"}
        )
        assert response.status_code == 200, response.text
    elif state in CLAIMED_STATES:
        auth = await _enroll(client, device, f"a12-{name}-inst")
        claimed = await client.post(
            "/companion/v2/tasks/claim", headers=auth, json={"leaseSeconds": 60}
        )
        assert claimed.status_code == 200, claimed.text
        assert claimed.json()["taskId"] == task_id
        lease_id = str(claimed.json()["leaseId"])
        if state != "PREFLIGHT":
            heartbeat = await client.post(
                f"/companion/v2/tasks/{task_id}/heartbeat",
                headers=auth,
                json={"leaseId": lease_id, "currentStep": 0, "leaseSeconds": 60},
            )
            assert heartbeat.status_code == 200, heartbeat.text
        if state in {"PAUSE_REQUESTED", "PAUSED_WAITING_USER", "RESUME_CHECK"}:
            response = await control(client, task_id, "pause", {"reason": "operator taking over"})
            assert response.status_code == 200, response.text
        if state in {"PAUSED_WAITING_USER", "RESUME_CHECK"}:
            response = await control(client, task_id, "ack-paused", {"leaseId": lease_id})
            assert response.status_code == 200, response.text
        if state == "RESUME_CHECK":
            response = await control(
                client,
                task_id,
                "resume",
                {"reason": "operator returned", "pageVerified": True},
            )
            assert response.status_code == 200, response.text
        if state == "CANCEL_REQUESTED":
            response = await control(client, task_id, "cancel", {"reason": "stop at safe point"})
            assert response.status_code == 200, response.text
        current = await view_task(client, task_id)
        assert current["state"] == state, current["state"]
        return task_id, device, auth, lease_id
    else:
        # WAITING_MATERIALS / SUCCEEDED / FAILED / EXPIRED: no API path reaches
        # these from a fresh task, so stage them directly.
        def mutate(row: MobileTaskRow) -> None:
            if state == "WAITING_MATERIALS":
                row.business_state = "WAITING_MATERIALS"
            elif state == "SUCCEEDED":
                row.status, row.business_state = "SUCCEEDED", "SUCCEEDED"
            elif state == "FAILED":
                row.status, row.business_state = "FAILED", "FAILED"
            elif state == "EXPIRED":
                row.business_state = "EXPIRED"
            else:
                raise AssertionError(f"unsupported state {state}")

        await patch_task(app, task_id, mutate)
    auth = await _enroll(client, device, f"a12-{name}-inst")
    current = await view_task(client, task_id)
    assert current["state"] == state, current["state"]
    return task_id, device, auth, lease_id


async def unknown_ledger_flow(
    client: httpx.AsyncClient, app: FastAPI, name: str, *, status: str
) -> tuple[str, str, dict[str, str], str]:
    """Frozen-steps delist task driven into RECONCILING with a ledger row."""
    device = await create_direct_device(client, f"a12-{name}")
    created = await _create_steps_task(
        client, device, delist_steps(0), f"a12-{name}-{uuid.uuid4()}"
    )
    assert created.status_code == 201, created.text
    task_id = str(created.json()["taskId"])
    auth = await _enroll(client, device, f"a12-{name}-inst")
    claimed = await client.post(
        "/companion/v2/tasks/claim", headers=auth, json={"leaseSeconds": 60}
    )
    assert claimed.status_code == 200, claimed.text
    lease_id = str(claimed.json()["leaseId"])
    heartbeat = await client.post(
        f"/companion/v2/tasks/{task_id}/heartbeat",
        headers=auth,
        json={"leaseId": lease_id, "currentStep": 2},
    )
    assert heartbeat.status_code == 200, heartbeat.text
    async with app.state.database.unit_of_work() as session:
        row = await session.get(MobileTaskRow, task_id)
        assert row is not None
        frozen = steps_action_identity(row)
    intent = await client.post(
        f"/companion/v2/tasks/{task_id}/actions/intent",
        headers=auth,
        json={
            "leaseId": lease_id,
            "actionId": frozen["action_id"],
            "actionKey": frozen["action_key"],
            "parameterHash": frozen["parameter_hash"],
            "beforeEvidence": "evidence://a12-before",
        },
    )
    assert intent.status_code == 201, intent.text
    outcome = await client.post(
        f"/companion/v2/tasks/{task_id}/actions/{frozen['action_key']}/outcome",
        headers=auth,
        json={
            "leaseId": lease_id,
            "parameterHash": frozen["parameter_hash"],
            "status": status,
            "evidence": "evidence://a12-post",
        },
    )
    assert outcome.status_code == 200, outcome.text
    return task_id, device, auth, lease_id


async def ledger_rows(app: FastAPI, task_id: str) -> list[MobileActionCommitRow]:
    async with app.state.database.unit_of_work() as session:
        return list(
            await session.scalars(
                select(MobileActionCommitRow).where(
                    MobileActionCommitRow.task_id == task_id
                )
            )
        )


async def device_lease(app: FastAPI, device: str) -> DeviceLeaseRow | None:
    async with app.state.database.unit_of_work() as session:
        return await session.get(DeviceLeaseRow, device)


# ---------------------------------------------------------------------------
# 1. The explicit control-transition matrix
# ---------------------------------------------------------------------------


def test_matrices_are_total_and_closed():
    """The code-level tables cover every business state with closed outcomes."""
    for matrix, outcomes in (
        (CANCEL_TRANSITIONS, CANCEL_OUTCOMES),
        (PAUSE_TRANSITIONS, PAUSE_OUTCOMES),
        (ACK_PAUSED_TRANSITIONS, ACK_PAUSED_OUTCOMES),
        (RESUME_TRANSITIONS, RESUME_OUTCOMES),
    ):
        assert set(matrix) == set(BUSINESS_STATES)
        assert set(matrix.values()) <= outcomes
    # Task-card pinning: queued/preflight/paused cancel immediately, running
    # defers, unknown must reconcile first, cancel/pause duplicates replay.
    assert CANCEL_TRANSITIONS["QUEUED"] == "CANCELLED_NOW"
    assert CANCEL_TRANSITIONS["PREFLIGHT"] == "CANCELLED_NOW"
    assert CANCEL_TRANSITIONS["PAUSED_WAITING_USER"] == "CANCELLED_NOW"
    assert CANCEL_TRANSITIONS["RUNNING"] == "CANCEL_REQUESTED"
    assert CANCEL_TRANSITIONS["RECONCILING"] == "REJECTED_RECONCILE_FIRST"
    assert CANCEL_TRANSITIONS["CANCELLED"] == "IDEMPOTENT_RETURN"
    assert ACK_PAUSED_TRANSITIONS["PAUSED_WAITING_USER"] == "IDEMPOTENT_RETURN"
    assert ACK_PAUSED_TRANSITIONS["RESUME_CHECK"] == "REJECTED_SUPERSEDED"
    assert PAUSE_TRANSITIONS["CANCEL_REQUESTED"] == "REJECTED_CANCEL_WINS"
    assert RESUME_TRANSITIONS["PAUSED_WAITING_USER"] == "RESUME_CHECK"


@pytest.mark.parametrize(
    "state,code,expected,delta",
    [
        ("QUEUED", 200, "CANCELLED", 1),
        ("WAITING_MATERIALS", 200, "CANCELLED", 1),
        ("PREFLIGHT", 200, "CANCELLED", 1),
        ("PAUSE_REQUESTED", 200, "CANCELLED", 1),
        ("PAUSED_WAITING_USER", 200, "CANCELLED", 1),
        ("RUNNING", 200, "CANCEL_REQUESTED", 1),
        ("RESUME_CHECK", 200, "CANCEL_REQUESTED", 1),
        ("CANCEL_REQUESTED", 200, "CANCEL_REQUESTED", 0),  # duplicate: idempotent
        ("CANCELLED", 200, "CANCELLED", 0),  # terminal: idempotent replay
        ("RECONCILING", 409, "RECONCILING", 0),  # unknown: reconcile first
        ("SUCCEEDED", 409, "SUCCEEDED", 0),
        ("FAILED", 409, "FAILED", 0),
        ("EXPIRED", 409, "EXPIRED", 0),
    ],
)
async def test_cancel_matrix_executed_per_state(api, state, code, expected, delta):
    client, _app = api
    task_id, *_rest = await task_in_state(client, _app, state=state, name=f"cancel-{state}")
    before = await view_task(client, task_id)
    response = await control(client, task_id, "cancel", {"reason": "matrix probe"})
    assert response.status_code == code, response.text
    after = await view_task(client, task_id)
    assert after["state"] == expected
    if expected == "CANCELLED":
        assert after["runnerStatus"] == "FAILED"
    assert (after["controlRevision"] or 0) - (before["controlRevision"] or 0) == delta


@pytest.mark.parametrize(
    "state,code,expected,delta",
    [
        ("QUEUED", 200, "PAUSE_REQUESTED", 1),
        ("PREFLIGHT", 200, "PAUSE_REQUESTED", 1),
        ("RUNNING", 200, "PAUSE_REQUESTED", 1),
        ("RESUME_CHECK", 200, "PAUSE_REQUESTED", 1),
        ("PAUSE_REQUESTED", 200, "PAUSE_REQUESTED", 0),  # duplicate: idempotent
        ("PAUSED_WAITING_USER", 200, "PAUSED_WAITING_USER", 0),
        ("CANCEL_REQUESTED", 409, "CANCEL_REQUESTED", 0),  # out-of-order: cancel wins
        ("RECONCILING", 409, "RECONCILING", 0),
        ("SUCCEEDED", 409, "SUCCEEDED", 0),
        ("FAILED", 409, "FAILED", 0),
        ("CANCELLED", 409, "CANCELLED", 0),
        ("EXPIRED", 409, "EXPIRED", 0),
    ],
)
async def test_pause_matrix_executed_per_state(api, state, code, expected, delta):
    client, _app = api
    task_id, _device, _auth, _lease = await task_in_state(
        client, _app, state=state, name=f"pause-{state}"
    )
    before = await view_task(client, task_id)
    response = await control(client, task_id, "pause", {"reason": "matrix probe"})
    assert response.status_code == code, response.text
    after = await view_task(client, task_id)
    assert after["state"] == expected
    assert (after["controlRevision"] or 0) - (before["controlRevision"] or 0) == delta


@pytest.mark.parametrize(
    "state,code,expected,delta",
    [
        ("QUEUED", 200, "PAUSED_WAITING_USER", 1),
        ("PREFLIGHT", 200, "PAUSED_WAITING_USER", 1),
        ("RUNNING", 200, "PAUSED_WAITING_USER", 1),
        ("PAUSE_REQUESTED", 200, "PAUSED_WAITING_USER", 1),
        ("PAUSED_WAITING_USER", 200, "PAUSED_WAITING_USER", 0),  # duplicate ack
        ("RESUME_CHECK", 409, "RESUME_CHECK", 0),  # out-of-order: superseded
        ("CANCEL_REQUESTED", 409, "CANCEL_REQUESTED", 0),  # out-of-order: cancel wins
        ("RECONCILING", 409, "RECONCILING", 0),
        ("SUCCEEDED", 409, "SUCCEEDED", 0),
        ("FAILED", 409, "FAILED", 0),
        ("CANCELLED", 409, "CANCELLED", 0),
        ("EXPIRED", 409, "EXPIRED", 0),
    ],
)
async def test_ack_paused_matrix_executed_per_state(api, state, code, expected, delta):
    client, _app = api
    task_id, _device, _auth, lease = await task_in_state(
        client, _app, state=state, name=f"ack-{state}"
    )
    before = await view_task(client, task_id)
    body = {"leaseId": lease} if lease else {}
    response = await control(client, task_id, "ack-paused", body)
    assert response.status_code == code, response.text
    after = await view_task(client, task_id)
    assert after["state"] == expected
    assert (after["controlRevision"] or 0) - (before["controlRevision"] or 0) == delta
    if state == "PAUSED_WAITING_USER":
        # Duplicate local confirmation: pauseAckAt is not re-stamped.
        assert after["pauseAckAt"] == before["pauseAckAt"]


async def test_commit_intent_redirects_cancel_and_ack_to_reconciliation(api):
    """commit-intent modifier: cancel refuses, ack redirects to RECONCILING."""
    client, app = api
    task_id, device, auth, lease = await task_in_state(
        client, app, state="RUNNING", name="commit-intent"
    )
    await patch_task(
        app,
        task_id,
        lambda row: setattr(
            row, "command_payload", {**(row.command_payload or {}), "commitIntent": True}
        ),
    )
    paused = await control(client, task_id, "pause", {"reason": "operator taking over"})
    assert paused.status_code == 200, paused.text
    # Cancel must not erase the uncertain post-commit outcome.
    denied = await control(client, task_id, "cancel", {"reason": "operator wants out"})
    assert denied.status_code == 409, denied.text
    assert "reconciled" in denied.json()["detail"].lower()
    acked = await control(client, task_id, "ack-paused", {"leaseId": lease})
    assert acked.status_code == 200, acked.text
    assert acked.json()["state"] == "RECONCILING"
    events = [event["event"] for event in acked.json()["controlEvents"]]
    assert events[-1] == "PAUSE_ACKED_RECONCILING"
    # Once RECONCILING every control path funnels into :reconcile.
    for action, body in (
        ("cancel", {"reason": "still wants out"}),
        ("resume", {"reason": "must not continue", "pageVerified": True}),
        ("retry", {"reason": "no blind retry"}),
    ):
        response = await control(client, task_id, action, body)
        assert response.status_code == 409, (action, response.text)


# ---------------------------------------------------------------------------
# 2. Persisted control events, revision, occupation release, idempotency
# ---------------------------------------------------------------------------


async def test_control_event_chain_monotonic_revision_and_audit(api):
    client, app = api
    task_id, device, auth, lease = await task_in_state(
        client, app, state="RUNNING", name="chain"
    )
    paused = await control(client, task_id, "pause", {"reason": "first reason"})
    assert paused.status_code == 200, paused.text
    first = await view_task(client, task_id)
    assert first["controlRevision"] == 1
    assert [event["event"] for event in first["controlEvents"]] == ["PAUSE_REQUESTED"]
    assert first["controlEvents"][0]["actor"].startswith("operator:")

    # Duplicate pause replays idempotently: no new revision, first reason wins.
    duplicate = await control(client, task_id, "pause", {"reason": "second reason"})
    assert duplicate.status_code == 200, duplicate.text
    second = await view_task(client, task_id)
    assert second["controlRevision"] == 1
    assert second["stallReason"] == "first reason"

    acked = await control(client, task_id, "ack-paused", {"leaseId": lease})
    assert acked.status_code == 200, acked.text
    third = await view_task(client, task_id)
    assert third["state"] == "PAUSED_WAITING_USER"
    assert third["controlRevision"] == 2
    assert [event["event"] for event in third["controlEvents"]] == [
        "PAUSE_REQUESTED",
        "PAUSE_ACKED",
    ]
    assert third["controlEvents"][1]["actor"] == "companion"

    duplicate_ack = await control(client, task_id, "ack-paused", {"leaseId": lease})
    assert duplicate_ack.status_code == 200, duplicate_ack.text
    fourth = await view_task(client, task_id)
    assert fourth["controlRevision"] == 2
    assert fourth["pauseAckAt"] == third["pauseAckAt"]

    resumed = await control(
        client, task_id, "resume", {"reason": "operator back", "pageVerified": True}
    )
    assert resumed.status_code == 200, resumed.text
    final = await view_task(client, task_id)
    assert final["controlRevision"] == 3
    assert [event["revision"] for event in final["controlEvents"]] == [1, 2, 3]

    actions = await audit_actions(app, task_id)
    assert actions == [
        "platform.task.pause_acked",
        "platform.task.pause_requested",
        "platform.task.resumed",
    ]


async def test_cancel_paused_releases_occupation_and_no_queue_zombie(api):
    """任务卡验收 1: 云取消本地 paused 后同设备无队头僵尸。"""
    client, app = api
    device = await create_direct_device(client, "a12-zombie")
    account = await create_account(client, "a12-zombie-acc")
    await bind(client, account, device)
    paused_id = await mint_probe_task(client, device, account, f"a12-zombie-p-{uuid.uuid4()}")
    next_id = await mint_probe_task(client, device, account, f"a12-zombie-n-{uuid.uuid4()}")
    auth = await _enroll(client, device, "a12-zombie-inst")
    claimed = await client.post(
        "/companion/v2/tasks/claim", headers=auth, json={"leaseSeconds": 60}
    )
    assert claimed.status_code == 200, claimed.text
    assert claimed.json()["taskId"] == paused_id
    lease_id = str(claimed.json()["leaseId"])
    heartbeat = await client.post(
        f"/companion/v2/tasks/{paused_id}/heartbeat",
        headers=auth,
        json={"leaseId": lease_id, "currentStep": 0},
    )
    assert heartbeat.status_code == 200, heartbeat.text
    acked = await control(client, paused_id, "ack-paused", {"leaseId": lease_id})
    assert acked.json()["state"] == "PAUSED_WAITING_USER"
    # The paused task still occupies the device lease until the cancel lands.
    live = await device_lease(app, device)
    assert live is not None and live.canceled_at is None

    cancelled = await control(client, paused_id, "cancel", {"reason": "operator gave up"})
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["state"] == "CANCELLED"
    # Occupation released with the cancel, not lazily at the next claim.
    released = await device_lease(app, device)
    assert released is not None and released.canceled_at is not None

    # No head-of-queue zombie: the same device immediately claims the next task.
    next_claim = await client.post(
        "/companion/v2/tasks/claim", headers=auth, json={"leaseSeconds": 60}
    )
    assert next_claim.status_code == 200, next_claim.text
    assert next_claim.json()["taskId"] == next_id

    replay = await control(client, paused_id, "cancel", {"reason": "operator gave up"})
    assert replay.status_code == 200, replay.text
    assert replay.json()["state"] == "CANCELLED"
    settled = await view_task(client, paused_id)
    assert settled["controlEvents"][-1]["event"] == "CANCELLED"


async def test_out_of_order_control_events_idempotent_or_refused(api):
    client, _app = api
    task_id, device, auth, lease = await task_in_state(
        client, _app, state="RUNNING", name="ooo"
    )
    soft = await control(client, task_id, "cancel", {"reason": "first cancel"})
    assert soft.status_code == 200 and soft.json()["state"] == "CANCEL_REQUESTED"
    first = await view_task(client, task_id)

    # Duplicate cancel (乱序重复): idempotent — revision and reason unchanged.
    replay = await control(client, task_id, "cancel", {"reason": "second cancel"})
    assert replay.status_code == 200, replay.text
    second = await view_task(client, task_id)
    assert second["controlRevision"] == first["controlRevision"]
    assert second["stallReason"] == "first cancel"

    # A late pause must not overwrite the sticky cancel decision.
    late_pause = await control(client, task_id, "pause", {"reason": "late pause"})
    assert late_pause.status_code == 409
    assert "cancelled" in late_pause.json()["detail"].lower()
    late_ack = await control(client, task_id, "ack-paused", {"leaseId": lease})
    assert late_ack.status_code == 409
    late_resume = await control(
        client, task_id, "resume", {"reason": "late resume", "pageVerified": True}
    )
    assert late_resume.status_code == 409
    assert (await view_task(client, task_id))["state"] == "CANCEL_REQUESTED"


# ---------------------------------------------------------------------------
# 3. KEEP_WAITING keeps pending actions; closure needs evidence + audit
# ---------------------------------------------------------------------------


async def test_keep_waiting_preserves_open_unknown_and_blocks_reclaim(api):
    """任务卡 #3 + fleet-identity/v1 §8: KEEP_WAITING 保留未决动作。"""
    client, app = api
    task_id, device, auth, lease = await unknown_ledger_flow(
        client, app, "keepwaiting", status="UNKNOWN"
    )
    waiting = await control(
        client,
        task_id,
        "reconcile",
        {"decision": "KEEP_WAITING", "evidence": "operator still verifying the listing"},
    )
    assert waiting.status_code == 200, waiting.text
    assert waiting.json()["state"] == "RECONCILING"
    rows = await ledger_rows(app, task_id)
    assert [row.status for row in rows] == ["UNKNOWN"]
    assert all(row.resolved_at is None for row in rows)
    assert all(row.resolution_revision == 0 for row in rows)

    # Open UNKNOWN keeps blocking reclaim for the whole device (KEEP_WAITING
    # semantics) — the pending action is preserved, not cleared.
    blocked = await client.post(
        "/companion/v2/tasks/claim", headers=auth, json={"leaseSeconds": 60}
    )
    assert blocked.status_code == 409, blocked.text
    assert "UNKNOWN" in blocked.json()["detail"]

    # Executor still live (lease alive): read-only window must stay closed.
    async with app.state.database.unit_of_work() as session:
        window = await evaluate_readonly_window(session, TENANT, device)
    assert window["verdict"] == "BLOCKED_EXECUTOR_LIVE"

    # Old executor proven stopped (lease expired + occupation canceled):
    def stop_executor(row: MobileTaskRow) -> None:
        row.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)

    await patch_task(app, task_id, stop_executor)
    async with app.state.database.unit_of_work() as session:
        lease_row = await session.get(DeviceLeaseRow, device, with_for_update=True)
        assert lease_row is not None
        lease_row.canceled_at = datetime.now(UTC)
        window = await evaluate_readonly_window(session, TENANT, device)
    assert window["verdict"] == "ALLOWED"
    assert window["proof"]["openUnknownActions"] == 1
    assert window["proof"]["reconcilingTasks"] == [task_id]

    # The window verdict never clears UNKNOWN nor unlocks the device: claim
    # keeps refusing until an explicit reconciliation converges the row.
    still_blocked = await client.post(
        "/companion/v2/tasks/claim", headers=auth, json={"leaseSeconds": 60}
    )
    assert still_blocked.status_code == 409, still_blocked.text
    assert [row.status for row in await ledger_rows(app, task_id)] == ["UNKNOWN"]

    settled = await control(
        client,
        task_id,
        "reconcile",
        {
            "decision": "CONFIRMED_NOT_SUBMITTED",
            "evidence": "platform listing page shows no such item id",
        },
    )
    assert settled.status_code == 200, settled.text
    assert settled.json()["state"] == "FAILED"
    rows = await ledger_rows(app, task_id)
    assert [row.status for row in rows] == ["NOT_SUBMITTED"]
    assert all(row.resolved_at is not None for row in rows)
    assert all(row.resolution_revision == 1 for row in rows)
    assert "platform.task.reconciled_keep_waiting" in await audit_actions(app, task_id)
    assert "platform.task.reconciled_not_submitted" in await audit_actions(app, task_id)

    # Unlock came from the explicit reconciliation only.
    unblocked = await client.post(
        "/companion/v2/tasks/claim", headers=auth, json={"leaseSeconds": 60}
    )
    assert unblocked.status_code == 204, unblocked.text


async def test_applied_contradicts_not_submitted_and_evidence_required(api):
    """任务卡验收 2: APPLIED 与 NOT_SUBMITTED 冲突拒绝；缺证据不得裁决未执行。"""
    client, app = api
    task_id, device, auth, lease = await unknown_ledger_flow(
        client, app, "applied", status="APPLIED"
    )
    conflict = await control(
        client,
        task_id,
        "reconcile",
        {"decision": "CONFIRMED_NOT_SUBMITTED", "evidence": "operator claims nothing sent"},
    )
    assert conflict.status_code == 409, conflict.text
    assert "contradicts" in conflict.json()["detail"]

    # Missing / too-short evidence is a request validation failure: no
    # adjudication of "not executed" without trusted evidence.
    missing = await client.post(
        f"/api/v1/platform-tasks/{task_id}:reconcile",
        headers=identity(),
        json={"decision": "CONFIRMED_NOT_SUBMITTED"},
    )
    assert missing.status_code == 422, missing.text
    thin = await control(
        client, task_id, "reconcile", {"decision": "CONFIRMED_NOT_SUBMITTED", "evidence": "ab"}
    )
    assert thin.status_code == 422, thin.text
    assert (await view_task(client, task_id))["state"] == "RECONCILING"

    no_item = await control(
        client,
        task_id,
        "reconcile",
        {"decision": "CONFIRMED_APPLIED", "evidence": "listing is live"},
    )
    assert no_item.status_code == 409, no_item.text

    confirmed = await control(
        client,
        task_id,
        "reconcile",
        {
            "decision": "CONFIRMED_APPLIED",
            "evidence": "listing is live under this id",
            "platformItemId": "xy-987654",
        },
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["state"] == "SUCCEEDED"
    assert confirmed.json()["result"]["platformItemId"] == "xy-987654"
    rows = await ledger_rows(app, task_id)
    assert [row.status for row in rows] == ["APPLIED"]
    assert all(row.resolution_revision == 1 for row in rows)
    assert "platform.task.reconciled_applied" in await audit_actions(app, task_id)


# ---------------------------------------------------------------------------
# Acceptance 3: pause → manual handling → resume keeps identity; other
# devices are never blocked by this pending task.
# ---------------------------------------------------------------------------


async def test_pause_manual_resume_preserves_identity_and_other_device_free(api):
    client, app = api
    device_a = await create_direct_device(client, "a12-identity-a")
    account_a = await create_account(client, "a12-identity-a-acc")
    await bind(client, account_a, device_a)
    device_b = await create_direct_device(client, "a12-identity-b")
    account_b = await create_account(client, "a12-identity-b-acc")
    await bind(client, account_b, device_b)
    task_a = await mint_probe_task(client, device_a, account_a, f"a12-id-a-{uuid.uuid4()}")
    task_b = await mint_probe_task(client, device_b, account_b, f"a12-id-b-{uuid.uuid4()}")
    auth_a = await _enroll(client, device_a, "a12-identity-a-inst")
    auth_b = await _enroll(client, device_b, "a12-identity-b-inst")

    claimed = await client.post(
        "/companion/v2/tasks/claim", headers=auth_a, json={"leaseSeconds": 60}
    )
    assert claimed.status_code == 200 and claimed.json()["taskId"] == task_a
    lease_id = str(claimed.json()["leaseId"])
    heartbeat = await client.post(
        f"/companion/v2/tasks/{task_a}/heartbeat",
        headers=auth_a,
        json={"leaseId": lease_id, "currentStep": 0},
    )
    assert heartbeat.status_code == 200, heartbeat.text
    paused = await control(client, task_a, "pause", {"reason": "manual handling"})
    assert paused.status_code == 200, paused.text
    acked = await control(client, task_a, "ack-paused", {"leaseId": lease_id})
    assert acked.json()["state"] == "PAUSED_WAITING_USER"

    before = await view_task(client, task_a)
    async with app.state.database.unit_of_work() as session:
        row = await session.get(MobileTaskRow, task_a)
        assert row is not None
        frozen_before = {
            "recipe": dict(row.recipe_pin or {}),
            "steps": [step for step in (row.steps or []) if step.get("action")],
            "attemptId": row.attempt_id,
        }

    # 异设备不被此未决任务卡住: device B claims its own task while A is paused.
    other = await client.post(
        "/companion/v2/tasks/claim", headers=auth_b, json={"leaseSeconds": 60}
    )
    assert other.status_code == 200, other.text
    assert other.json()["taskId"] == task_b

    resumed = await control(
        client, task_a, "resume", {"reason": "manual handling done", "pageVerified": True}
    )
    assert resumed.status_code == 200, resumed.text
    after = await view_task(client, task_a)
    assert after["taskId"] == task_a  # same task, not a re-mint
    assert after["commandPayload"] == before["commandPayload"]
    assert after["snapshotSha256"] == before["snapshotSha256"]
    assert after["attemptId"] == before["attemptId"]
    async with app.state.database.unit_of_work() as session:
        row = await session.get(MobileTaskRow, task_a)
        assert row is not None
        assert dict(row.recipe_pin or {}) == frozen_before["recipe"]
        assert [step for step in (row.steps or []) if step.get("action")] == frozen_before["steps"]
        assert row.attempt_id == frozen_before["attemptId"]
        resumed_lease_id = row.lease_id

    # The resumed original keeps running under its own lease.
    resumed_lease = after["controlEpoch"]
    assert resumed_lease
    continued = await client.post(
        f"/companion/v2/tasks/{task_a}/heartbeat",
        headers=auth_a,
        json={"leaseId": resumed_lease_id, "currentStep": 0},
    )
    assert continued.status_code == 200, continued.text
    assert continued.json()["businessState"] == "RUNNING"


async def test_postgres_paused_device_does_not_block_other_device_claim(pg_url):
    """验收 3 (真实 PG): 设备 A 的人工等待不阻塞设备 B 跨进程领取。"""
    async with api_process(pg_url) as (client, app):
        device_a = await create_direct_device(client, "a12-pg-paused")
        account_a = await create_account(client, "a12-pg-paused-acc")
        await bind(client, account_a, device_a)
        device_b = await create_direct_device(client, "a12-pg-free")
        account_b = await create_account(client, "a12-pg-free-acc")
        await bind(client, account_b, device_b)
        task_a = await mint_probe_task(client, device_a, account_a, f"a12-pg-a-{uuid.uuid4()}")
        task_b = await mint_probe_task(client, device_b, account_b, f"a12-pg-b-{uuid.uuid4()}")
        auth_a = await _enroll(client, device_a, "a12-pg-a-inst")
        auth_b = await _enroll(client, device_b, "a12-pg-b-inst")
        claimed = await client.post(
            "/companion/v2/tasks/claim", headers=auth_a, json={"leaseSeconds": 60}
        )
        assert claimed.status_code == 200 and claimed.json()["taskId"] == task_a
        lease_id = str(claimed.json()["leaseId"])
        heartbeat = await client.post(
            f"/companion/v2/tasks/{task_a}/heartbeat",
            headers=auth_a,
            json={"leaseId": lease_id, "currentStep": 0},
        )
        assert heartbeat.status_code == 200, heartbeat.text
        paused = await control(client, task_a, "pause", {"reason": "manual handling"})
        assert paused.status_code == 200, paused.text
        acked = await control(client, task_a, "ack-paused", {"leaseId": lease_id})
        assert acked.json()["state"] == "PAUSED_WAITING_USER"
        cancelled = await control(client, task_a, "cancel", {"reason": "abandon"})
        assert cancelled.status_code == 200 and cancelled.json()["state"] == "CANCELLED"

    async with api_process(pg_url) as (client2, _app2):
        other = await client2.post(
            "/companion/v2/tasks/claim", headers=auth_b, json={"leaseSeconds": 60}
        )
        assert other.status_code == 200, other.text
        assert other.json()["taskId"] == task_b


# ---------------------------------------------------------------------------
# 4. Read-only window proof
# ---------------------------------------------------------------------------


async def test_readonly_window_needs_stopped_executor_and_free_occupancy(api):
    client, app = api
    task_id, device, auth, lease = await task_in_state(
        client, app, state="PAUSED_WAITING_USER", name="window"
    )
    # Live executor (paused task still holds its lease): window closed.
    async with app.state.database.unit_of_work() as session:
        window = await evaluate_readonly_window(session, TENANT, device)
    assert window["verdict"] == "BLOCKED_EXECUTOR_LIVE"
    assert window["proof"]["executorLiveTasks"][0]["taskId"] == task_id

    # Executor stopped (task settled + occupation released by the cancel).
    cancelled = await control(client, task_id, "cancel", {"reason": "window probe"})
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["state"] == "CANCELLED"
    async with app.state.database.unit_of_work() as session:
        window = await evaluate_readonly_window(session, TENANT, device)
    assert window["verdict"] == "ALLOWED"
    assert window["proof"]["liveLeases"] == []

    # A live REMOTE occupancy keeps the window closed even with no executor.
    # (device_lease is one row per device — the canceled AUTO occupation is
    # replaced in place by a fresh REMOTE occupancy.)
    async with app.state.database.unit_of_work() as session:
        lease_row = await session.get(DeviceLeaseRow, device, with_for_update=True)
        assert lease_row is not None
        lease_row.lease_id = str(uuid.uuid4())
        lease_row.owner_workflow_id = "remote/session-x"
        lease_row.fencing_token = 99
        lease_row.expires_at = datetime.now(UTC) + timedelta(minutes=5)
        lease_row.canceled_at = None
        lease_row.owner_type = "REMOTE"
    async with app.state.database.unit_of_work() as session:
        window = await evaluate_readonly_window(session, TENANT, device)
    assert window["verdict"] == "BLOCKED_OCCUPANCY_LIVE"
    assert window["proof"]["liveLeases"][0]["ownerType"] == "REMOTE"
