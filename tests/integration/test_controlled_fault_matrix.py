"""Q12 controlled fault matrix: fault ledger and recovery fixtures (test line).

Contract anchors:
- fleet-identity/v1@20260916.1 §2/§4 (per-process session registry; a lease
  minted under a superseded session/boot is a stale authorization envelope),
  §5 (four-state mapping), §8 (release/reclaim guards, open-UNKNOWN blocks
  reclaim, UNKNOWN is never erased by cancel),
- task-schedule/v1 §4 via ``cloudctl_api.platform_tasks`` (cancel/pause/
  ack-paused/resume transition matrices, persisted control events with a
  per-task monotonic revision),
- ui-observation/v1@20260916.1 §4 (InputProof: preempted/inconclusive input
  fails closed — never continues into an irreversible commit).

Five mandated fault families from the Q12 task card, each asserted with the
ACTUAL execution count (action-ledger rows + audit events — never the
companion's own claim about what it did) and an EXTERNAL independently
observable end state (database rows / control-event chains):

- F1 intent lost-ACK: the intent POST committed server-side but its response
  was lost; the replayed identical intent must be absorbed (RECONCILE_REQUIRED,
  no second AUTHORIZED, one ledger row, one audit row), and after a lease
  partition the task must never be re-dispatched as fresh work — not even from
  another API process.
- F2 accessibility rebind: the companion process re-registers (fresh
  sessionId); late heartbeats under the old lease are stale envelopes; the
  task recovers via re-claim under the new session with the frozen steps
  identity unchanged. A transport heartbeat (page reopen analog) must NOT
  mint or revoke sessions — this is the server-side half of the
  process-restart vs page-reopen distinction.
- F3 cancel/recovery: pause -> manual -> resume keeps the task identity
  frozen; cancel of a RUNNING task converges through the fail path and frees
  the device; cancel never erases an open UNKNOWN.
- F4 old lease: after re-claim every companion channel under the previous
  lease is rejected; a committed intent survives lease loss without a second
  dispatch (KEEP_WAITING semantics).
- F5 input focus preemption: the ime executable gate stops dispatch while
  input is not ready, and a mid-run preemption terminates fail-closed with
  ZERO gated strikes in the ledger.

Side-effect policy (acceptance): companions are simulated by this test; only
the frozen maintenance/probe command families are used; Q03 real publishing is
NOT used to create base data for any Q02-derived scenario. The real-shop
cardIndex=0 targeting of the old Q02-B device scenarios is replaced by the
extended acceptance-target fixture (unique-token target card + confirm
dialog); the on-device items are declared below and skipped with stable
reasons — software results and device-pending items are counted separately in
``test_q12_software_and_device_item_accounting``.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import socket
import subprocess
import uuid
from collections.abc import AsyncIterator
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
from cloudctl_api.fleet_identity import (
    EXECUTABLE_GATE_ORDER,
    FleetSessionRow,
    ReconcileRequiredError,
)
from cloudctl_api.mobile_actions import canonical_steps, steps_action_identity
from cloudctl_api.platform_tasks import (
    BUSINESS_STATES,
    CANCEL_TRANSITIONS,
    RESUME_TRANSITIONS,
)
from cloudctl_api.settings import Settings
from fastapi import FastAPI
from sqlalchemy import select
from test_platform_tasks import (
    _enroll,
    create_direct_device,
    identity,
)
from test_xianyu_maintenance import _create_steps_task, delist_steps, polish_steps

POSTGRES_ENV = {**os.environ, "LC_ALL": "C", "LANG": "C", "LANGUAGE": "C"}

# ---------------------------------------------------------------------------
# Scenario matrix (the Q12 gate definition, pinned by the first test)
# ---------------------------------------------------------------------------

# The five fault families mandated by the task card. Each entry names the
# guard that must hold and the observable that proves it; the pinning test
# asserts the guards against the implementation constants so the matrix can
# never silently drift away from the shipped code.
FAMILY_INTENT_ACK_LOSS = "intent-ack-loss"
FAMILY_ACCESSIBILITY_REBIND = "accessibility-rebind"
FAMILY_CANCEL_RECOVERY = "cancel-recovery"
FAMILY_OLD_LEASE = "old-lease"
FAMILY_INPUT_FOCUS_PREEMPTION = "input-focus-preemption"

MANDATED_FAULT_FAMILIES = (
    FAMILY_INTENT_ACK_LOSS,
    FAMILY_ACCESSIBILITY_REBIND,
    FAMILY_CANCEL_RECOVERY,
    FAMILY_OLD_LEASE,
    FAMILY_INPUT_FOCUS_PREEMPTION,
)

SOFTWARE_SCENARIOS: dict[str, dict[str, Any]] = {
    "F1-intent-ack-loss": {
        "family": FAMILY_INTENT_ACK_LOSS,
        "fault": "intent committed, HTTP response lost, identical replay",
        "guard": "replay -> 200 RECONCILE_REQUIRED, never a second AUTHORIZED",
        "errorCode": (ReconcileRequiredError.status, ReconcileRequiredError.code),
        "executionCount": "mobile.action.intent audit rows == 1; ledger rows == 1",
        "observable": "ledger row status chain INTENT->UNKNOWN->NOT_SUBMITTED",
    },
    "F1-partition-no-redispatch": {
        "family": FAMILY_INTENT_ACK_LOSS,
        "fault": "lease partition after committed intent, re-claim via 2nd process",
        "guard": "claim returns 204; task RECONCILING; attempt stays 1",
        "errorCode": None,
        "executionCount": "ledger rows == 1 across both processes",
        "observable": "same INTENT row visible from both API processes",
    },
    "F2-accessibility-rebind": {
        "family": FAMILY_ACCESSIBILITY_REBIND,
        "fault": "companion process re-registration (accessibility rebind)",
        "guard": "old-lease heartbeat -> 409 stale envelope; transport heartbeat mints no session",
        "errorCode": (409, "AUTHORIZATION_ENVELOPE_STALE"),
        "executionCount": "gated strikes <= 1 across the whole cycle",
        "observable": "steps[0].fleetSessionId flips to the new sessionId; "
        "payloadIdentity byte-identical",
    },
    "F3-pause-manual-resume": {
        "family": FAMILY_CANCEL_RECOVERY,
        "fault": "operator pause mid-run, manual handling, verified resume",
        "guard": "identity frozen; control events monotonic revision 1..3",
        "errorCode": None,
        "executionCount": "controlRevision == 3; strikes == 0 before settle",
        "observable": "taskId/attemptId/snapshotSha256 unchanged after resume",
    },
    "F3-cancel-running-convergence": {
        "family": FAMILY_CANCEL_RECOVERY,
        "fault": "operator cancel while RUNNING, companion honors at safe point",
        "guard": "CANCEL_REQUESTED -> fail path -> CANCELLED, device freed",
        "errorCode": None,
        "executionCount": "ledger strikes == 0; next task claimable at once",
        "observable": "FAILED + errorCode CANCELLED; lease canceled; queue "
        "head not blocked (no zombie)",
    },
    "F3-cancel-unknown-preserved": {
        "family": FAMILY_CANCEL_RECOVERY,
        "fault": "operator cancel while an UNKNOWN outcome is open",
        "guard": "409 reconcile-first; UNKNOWN survives cancel and blocks reclaim (KEEP_WAITING)",
        "errorCode": (409, "RECONCILE_REQUIRED"),
        "executionCount": "UNKNOWN rows stay 1 with resolved_at NULL",
        "observable": "claim 409 until explicit operator reconciliation",
    },
    "F4-old-lease-channels": {
        "family": FAMILY_OLD_LEASE,
        "fault": "lease lapse + re-claim; previous lease replayed",
        "guard": "heartbeat/events/complete/release under old lease all 409",
        "errorCode": None,
        "executionCount": "exactly one live lease; fencing token increased",
        "observable": "attempt 2 + new leaseId; controlEpoch strictly higher",
    },
    "F4-committed-intent-no-redispatch": {
        "family": FAMILY_OLD_LEASE,
        "fault": "lease loss after committed intent; late outcome under any lease",
        "guard": "no re-dispatch (claim 204, KEEP_WAITING); outcome channels "
        "rejected; ledger stays INTENT",
        "errorCode": None,
        "executionCount": "authorized strikes == 1 forever (single INTENT row)",
        "observable": "task RECONCILING, attempt 1, ledger INTENT unresolved",
    },
    "F5-ime-gate": {
        "family": FAMILY_INPUT_FOCUS_PREEMPTION,
        "fault": "input not ready (IME preempted) at claim time",
        "guard": "executable gate ime=false -> claim 204 (no dispatch)",
        "errorCode": None,
        "executionCount": "strikes == 0 while the gate is closed",
        "observable": "fleet envelope failedGates == ['ime']; claim 200 only after IME restored",
    },
    "F5-focus-preemption-fail-closed": {
        "family": FAMILY_INPUT_FOCUS_PREEMPTION,
        "fault": "input focus stolen mid-run (ui-observation/v1 §4 InputProof)",
        "guard": "terminate fail-closed; never reach the gated commit",
        "errorCode": None,
        "executionCount": "ledger strikes == 0 despite two claim cycles",
        "observable": "FAILED + errorCode INPUT_FOCUS_PREEMPTED; lease "
        "released; next task dispatched",
    },
}

SOFTWARE_TEST_NAMES = (
    "test_q12_scenario_matrix_definition_pinned",
    "test_f1_intent_ack_loss_replay_never_reauthorizes",
    "test_f1_partition_after_committed_intent_never_redispatches_cross_process",
    "test_f2_accessibility_rebind_stale_envelope_then_identity_preserving_recovery",
    "test_f2_late_gated_intent_under_superseded_session_rejected",
    "test_f3_pause_manual_resume_recovery_keeps_identity",
    "test_f3_cancel_running_converges_and_frees_device",
    "test_f3_cancel_refused_while_unknown_open_and_keep_waiting_blocks_reclaim",
    "test_f4_old_lease_rejected_on_every_companion_channel_after_reclaim",
    "test_f4_committed_intent_survives_lease_loss_without_second_dispatch",
    "test_f5_ime_gate_blocks_dispatch_until_input_ready",
    "test_f5_midrun_focus_preemption_fails_closed_with_zero_strikes",
    "test_q12_software_and_device_item_accounting",
)

# On-device (hardware) items: honestly declared, skipped in software runs,
# counted separately. The acceptance-target extension is the fixture that
# makes each item non-vacuous (Q02-B lesson: no assertion without an
# externally observable state change).
DEVICE_PENDING_ITEMS: tuple[dict[str, str], ...] = (
    {
        "id": "q12-device-process-restart-not-page-reopen",
        "aspect": "process restart vs page reopen distinguishable on device",
        "owner": "Q13 device line",
        "fixture": "acceptance-target boot_marker BOOT#<process_boots> vs "
        "PAGE#<page_opens>; a real force-stop/reboot must increment BOOT#, a "
        "mere page reopen must not (anti hollow-pass marker)",
    },
    {
        "id": "q12-device-accessibility-rebind",
        "aspect": "accessibility service off/on mid-task",
        "owner": "Q13 device line (B10/B11)",
        "fixture": "server projection covered by F2; on-device half needs a "
        "real companion process re-registration during a live lease",
    },
    {
        "id": "q12-device-ime-focus-preemption",
        "aspect": "input focus stolen mid-input on a real IME",
        "owner": "Q13 device line (B14)",
        "fixture": "acceptance-target focus_thief_button steals input_field "
        "focus; execution_ledger FOCUS_LOSS counter is the external "
        "observable; companion must terminate fail-closed with zero strikes",
    },
    {
        "id": "q12-device-unique-target-confirm-strike",
        "aspect": "gated confirm strike on a unique target (no cardIndex=0)",
        "owner": "Q13 device line",
        "fixture": "acceptance-target arm_button mints TARGET_TOKEN <uuid>, "
        "confirm dialog embeds the token, result_panel shows STRUCK <token>; "
        "requires a controller decision to allowlist the testtarget package "
        "in the companion locator registry (see report)",
    },
)


# ---------------------------------------------------------------------------
# App fixtures (in-memory SQLite for the functional matrix; disposable
# PostgreSQL for the cross-process proof — SQLite must never stand in)
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
    root = tmp_path_factory.mktemp("q12-postgres")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    subprocess.run(  # noqa: S603 - fixed PostgreSQL tools and test-owned paths
        ["initdb", "-D", str(root / "data"), "-A", "trust", "-U", "q12test"],  # noqa: S607
        check=True,
        capture_output=True,
        env=POSTGRES_ENV,
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
        env=POSTGRES_ENV,
    )
    try:
        yield port
    finally:
        subprocess.run(  # noqa: S603 - fixed PostgreSQL tools and test-owned paths
            ["pg_ctl", "-D", str(root / "data"), "-m", "immediate", "-w", "stop"],  # noqa: S607
            check=True,
            capture_output=True,
            env=POSTGRES_ENV,
        )
        shutil.rmtree(root, ignore_errors=True)


@pytest.fixture
def pg_url(isolated_postgres):
    name = "q12_" + uuid.uuid4().hex
    subprocess.run(  # noqa: S603 - fixed PostgreSQL tools and test-owned paths
        ["createdb", "-h", "127.0.0.1", "-p", str(isolated_postgres), "-U", "q12test", name],  # noqa: S607
        check=True,
        capture_output=True,
        env=POSTGRES_ENV,
    )
    return f"postgresql+asyncpg://q12test@127.0.0.1:{isolated_postgres}/{name}"


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
# Simulated companion + shared helpers
# ---------------------------------------------------------------------------


def full_capabilities() -> dict[str, Any]:
    """All-gates-green closed capability table (fleet-identity/v1 §3)."""
    return {
        "accessibility": {"supported": True, "engineMin": 1},
        "ime": {"supported": True, "engineMin": 1},
        "screen_capture": {"supported": True, "engineMin": 1},
        "media_projection": {"supported": False},
        "flutter_anchors": {"supported": True, "engineMin": 2},
        "im_listen": {"supported": True, "engineMin": 1},
    }


async def register_fleet_session(
    app: FastAPI,
    auth: dict[str, str],
    *,
    boot_id: str,
    ime_ready: bool = True,
) -> dict[str, Any]:
    """Companion process registration (fleet-identity/v1 §2): mints a fresh
    sessionId and revokes the device's prior sessions."""
    service = app.state.mobile_task_service
    token = auth["Authorization"].split(" ", 1)[1]
    binding = await service.authenticate(token)
    return await service.register_fleet_session(
        binding,
        boot_id=boot_id,
        companion_version="1.0.0",
        capabilities=full_capabilities(),
        accessibility_enabled=True,
        accessibility_active=True,
        ime_ready=ime_ready,
        screen_unlocked=True,
        engine_version=2,
    )


async def claim(client: httpx.AsyncClient, auth: dict[str, str]) -> httpx.Response:
    return await client.post("/companion/v2/tasks/claim", headers=auth, json={"leaseSeconds": 60})


async def heartbeat(
    client: httpx.AsyncClient,
    auth: dict[str, str],
    task_id: str,
    lease_id: str,
    *,
    step: int = 0,
) -> httpx.Response:
    return await client.post(
        f"/companion/v2/tasks/{task_id}/heartbeat",
        headers=auth,
        json={"leaseId": lease_id, "currentStep": step, "leaseSeconds": 60},
    )


async def control(
    client: httpx.AsyncClient, task_id: str, action: str, body: dict[str, Any]
) -> httpx.Response:
    return await client.post(
        f"/api/v1/platform-tasks/{task_id}:{action}",
        headers=identity(),
        json=body,
    )


async def view_task(client: httpx.AsyncClient, task_id: str) -> dict[str, Any]:
    response = await client.get(f"/api/v1/platform-tasks/{task_id}", headers=identity())
    assert response.status_code == 200, response.text
    return response.json()


async def mint_steps_task(
    client: httpx.AsyncClient, device: str, steps: list[dict[str, Any]], name: str
) -> str:
    created = await _create_steps_task(client, device, steps, f"q12-{name}-{uuid.uuid4()}")
    assert created.status_code == 201, created.text
    return str(created.json()["taskId"])


async def provision(client: httpx.AsyncClient, name: str) -> tuple[str, dict[str, str]]:
    """Fresh device + enrolled companion binding."""
    device = await create_direct_device(client, f"q12-{name}")
    auth = await _enroll(client, device, f"q12-{name}-instance")
    return device, auth


async def running_delist_task(
    client: httpx.AsyncClient, app: FastAPI, name: str, *, boot_id: str
) -> dict[str, Any]:
    """Fleet-registered companion with a claimed+RUNNING frozen delist task."""
    device, auth = await provision(client, name)
    await register_fleet_session(app, auth, boot_id=boot_id)
    task_id = await mint_steps_task(client, device, delist_steps(0), name)
    claimed = await claim(client, auth)
    assert claimed.status_code == 200, claimed.text
    body = claimed.json()
    assert body["taskId"] == task_id
    lease_id = str(body["leaseId"])
    started = await heartbeat(client, auth, task_id, lease_id, step=2)
    assert started.status_code == 200, started.text
    async with app.state.database.unit_of_work() as session:
        row = await session.get(MobileTaskRow, task_id)
        assert row is not None
        frozen = steps_action_identity(row)
    return {
        "deviceId": device,
        "auth": auth,
        "taskId": task_id,
        "leaseId": lease_id,
        "claim": body,
        "frozen": frozen,
    }


def intent_body(frozen: dict[str, Any], lease_id: str, before_evidence: str) -> dict[str, Any]:
    return {
        "leaseId": lease_id,
        "actionId": frozen["action_id"],
        "actionKey": frozen["action_key"],
        "parameterHash": frozen["parameter_hash"],
        "beforeEvidence": before_evidence,
    }


async def post_intent(
    client: httpx.AsyncClient,
    auth: dict[str, str],
    task_id: str,
    frozen: dict[str, Any],
    lease_id: str,
    before_evidence: str,
) -> httpx.Response:
    return await client.post(
        f"/companion/v2/tasks/{task_id}/actions/intent",
        headers=auth,
        json=intent_body(frozen, lease_id, before_evidence),
    )


async def post_outcome(
    client: httpx.AsyncClient,
    auth: dict[str, str],
    task_id: str,
    frozen: dict[str, Any],
    lease_id: str,
    status: str,
    evidence: str,
) -> httpx.Response:
    return await client.post(
        f"/companion/v2/tasks/{task_id}/actions/{frozen['action_key']}/outcome",
        headers=auth,
        json={
            "leaseId": lease_id,
            "parameterHash": frozen["parameter_hash"],
            "status": status,
            "evidence": evidence,
        },
    )


def problem_code(response: httpx.Response) -> tuple[int, str]:
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    return response.status_code, str(body["code"])


async def task_row(app: FastAPI, task_id: str) -> MobileTaskRow:
    async with app.state.database.unit_of_work() as session:
        row = await session.get(MobileTaskRow, task_id)
        assert row is not None
        return row


async def ledger_rows(app: FastAPI, task_id: str) -> list[MobileActionCommitRow]:
    async with app.state.database.unit_of_work() as session:
        return list(
            await session.scalars(
                select(MobileActionCommitRow).where(MobileActionCommitRow.task_id == task_id)
            )
        )


async def audit_actions(app: FastAPI, action_key: str) -> list[str]:
    """Ledger audit trail for one controlled action (resource_id = actionKey).

    The audit rows are the ACTUAL-execution witness: intent/outcome audits are
    written only when the ledger transitions, never on idempotent replays.
    """
    async with app.state.database.unit_of_work() as session:
        rows = list(
            await session.scalars(
                select(AuditEventRow).where(
                    AuditEventRow.resource_id == action_key,
                    AuditEventRow.action.like("mobile.action.%"),
                )
            )
        )
    return sorted(row.action for row in rows)


async def live_lease(app: FastAPI, device: str) -> DeviceLeaseRow | None:
    async with app.state.database.unit_of_work() as session:
        return await session.get(DeviceLeaseRow, device)


async def active_fleet_session_id(app: FastAPI, device: str) -> str | None:
    async with app.state.database.unit_of_work() as session:
        row = await session.scalar(
            select(FleetSessionRow)
            .where(
                FleetSessionRow.device_id == device,
                FleetSessionRow.revoked_at.is_(None),
            )
            .order_by(FleetSessionRow.created_at.desc())
        )
    return row.session_id if row is not None else None


async def expire_lease(app: FastAPI, task_id: str) -> None:
    """Simulate the network partition: the lease lapses with no heartbeats."""
    async with app.state.database.unit_of_work() as session:
        row = await session.get(MobileTaskRow, task_id)
        assert row is not None
        row.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)


def real_steps_payload_identity(row: MobileTaskRow) -> str:
    real = [step for step in (row.steps or []) if step.get("action")]
    return hashlib.sha256(canonical_steps(real).encode()).hexdigest()


# ---------------------------------------------------------------------------
# 0. The matrix is pinned against the shipped implementation
# ---------------------------------------------------------------------------


async def test_q12_scenario_matrix_definition_pinned() -> None:
    """The scenario table is the Q12 gate definition — keep it honest."""
    from cloudctl_api.fleet_identity import AuthorizationEnvelopeStaleError

    # Every mandated fault family is covered by at least one scenario.
    covered = {entry["family"] for entry in SOFTWARE_SCENARIOS.values()}
    assert covered == set(MANDATED_FAULT_FAMILIES)
    # The transition matrices stay total-and-closed (A12 invariant reused here
    # because F3 asserts against them).
    assert set(CANCEL_TRANSITIONS) == set(BUSINESS_STATES)
    assert set(RESUME_TRANSITIONS) == set(BUSINESS_STATES)
    assert CANCEL_TRANSITIONS["RUNNING"] == "CANCEL_REQUESTED"
    assert CANCEL_TRANSITIONS["RECONCILING"] == "REJECTED_RECONCILE_FIRST"
    assert RESUME_TRANSITIONS["PAUSED_WAITING_USER"] == "RESUME_CHECK"
    # Guard codes wired to the implementation constants.
    assert SOFTWARE_SCENARIOS["F2-accessibility-rebind"]["errorCode"] == (
        AuthorizationEnvelopeStaleError.status,
        AuthorizationEnvelopeStaleError.code,
    )
    for key in ("F1-intent-ack-loss", "F3-cancel-unknown-preserved"):
        assert SOFTWARE_SCENARIOS[key]["errorCode"] == (
            ReconcileRequiredError.status,
            ReconcileRequiredError.code,
        )
    # F5 guards reference the frozen executable gate order (ime is a gate).
    assert "ime" in EXECUTABLE_GATE_ORDER
    # Device-pending items are declared with non-vacuous fixture markers.
    assert len(DEVICE_PENDING_ITEMS) == 4
    assert all(item["fixture"] for item in DEVICE_PENDING_ITEMS)
    print(f"\n[Q12 matrix] software scenarios: {len(SOFTWARE_SCENARIOS)}")
    for key, entry in SOFTWARE_SCENARIOS.items():
        print(f"[Q12 scenario] {key} — {entry['fault']} | guard: {entry['guard']}")


# ---------------------------------------------------------------------------
# F1: intent lost-ACK
# ---------------------------------------------------------------------------


async def test_f1_intent_ack_loss_replay_never_reauthorizes(api):
    """ACK loss: identical intent replay is absorbed, never re-authorized."""
    client, app = api
    ctx = await running_delist_task(client, app, "f1-ack", boot_id="q12-boot-f1")
    task_id, lease, frozen = ctx["taskId"], ctx["leaseId"], ctx["frozen"]

    # The intent commits server-side but its 201 response is lost on the wire.
    first = await post_intent(client, ctx["auth"], task_id, frozen, lease, "evidence://q12-before")
    assert first.status_code == 201, first.text
    assert first.json()["decision"] == "AUTHORIZED"

    # The companion, not knowing the first POST landed, replays it verbatim.
    replay = await post_intent(client, ctx["auth"], task_id, frozen, lease, "evidence://q12-before")
    assert replay.status_code == 200, replay.text
    assert replay.json()["decision"] == "RECONCILE_REQUIRED"
    assert replay.json()["action"]["actionKey"] == frozen["action_key"]

    # A divergent replay (the companion changed its evidence story) is refused.
    divergent = await post_intent(
        client, ctx["auth"], task_id, frozen, lease, "evidence://q12-other-before"
    )
    assert divergent.status_code == 409, divergent.text

    # ACTUAL execution count: one ledger row, one intent audit row — the
    # replay executed nothing.
    rows = await ledger_rows(app, task_id)
    assert [row.status for row in rows] == ["INTENT"]
    assert await audit_actions(app, frozen["action_key"]) == ["mobile.action.intent"]
    row = await task_row(app, task_id)
    assert row.business_state == "RECONCILING"

    # The strike outcome is UNKNOWN (partition during the strike), reported
    # while the lease is still live; replays stay idempotent.
    outcome = await post_outcome(
        client, ctx["auth"], task_id, frozen, lease, "UNKNOWN", "evidence://q12-lost"
    )
    assert outcome.status_code == 200, outcome.text
    outcome_replay = await post_outcome(
        client, ctx["auth"], task_id, frozen, lease, "UNKNOWN", "evidence://q12-lost"
    )
    assert outcome_replay.status_code == 200, outcome_replay.text
    divergent_outcome = await post_outcome(
        client, ctx["auth"], task_id, frozen, lease, "APPLIED", "evidence://q12-lost"
    )
    assert divergent_outcome.status_code == 409, divergent_outcome.text

    # External observables: UNKNOWN row unresolved, audit intent+outcome once.
    rows = await ledger_rows(app, task_id)
    assert [row.status for row in rows] == ["UNKNOWN"]
    assert all(row.resolved_at is None for row in rows)
    assert await audit_actions(app, frozen["action_key"]) == [
        "mobile.action.intent",
        "mobile.action.outcome",
    ]

    # Open UNKNOWN blocks the device from new work (KEEP_WAITING semantics).
    blocked = await claim(client, ctx["auth"])
    status, code = problem_code(blocked)
    assert (status, code) == (409, "RECONCILE_REQUIRED")

    # Operator reconciliation converges the row and unblocks the device.
    settled = await control(
        client,
        task_id,
        "reconcile",
        {
            "decision": "CONFIRMED_NOT_SUBMITTED",
            "evidence": "fixture target token never appeared in the strike ledger",
        },
    )
    assert settled.status_code == 200, settled.text
    assert settled.json()["state"] == "FAILED"
    rows = await ledger_rows(app, task_id)
    assert [row.status for row in rows] == ["NOT_SUBMITTED"]
    assert all(row.resolved_at is not None for row in rows)
    empty = await claim(client, ctx["auth"])
    assert empty.status_code == 204, empty.text
    print(
        f"\n[Q12/F1] strikes authorized=1 (audit rows: "
        f"{await audit_actions(app, frozen['action_key'])}), ledger "
        "INTENT->UNKNOWN->NOT_SUBMITTED"
    )


async def test_f1_partition_after_committed_intent_never_redispatches_cross_process(pg_url):
    """Partition after a committed intent: the other API process never
    re-dispatches the task as fresh work (fleet-identity/v1 §8)."""
    async with (
        api_process(pg_url) as (client1, app1),
        api_process(pg_url) as (
            client2,
            app2,
        ),
    ):
        device, auth = await provision(client1, "f1-part")
        await register_fleet_session(app1, auth, boot_id="q12-boot-f1p")
        task_id = await mint_steps_task(client1, device, delist_steps(0), "f1-part")
        claimed = await claim(client1, auth)
        assert claimed.status_code == 200, claimed.text
        lease_id = str(claimed.json()["leaseId"])
        started = await heartbeat(client1, auth, task_id, lease_id, step=2)
        assert started.status_code == 200, started.text
        async with app1.state.database.unit_of_work() as session:
            row = await session.get(MobileTaskRow, task_id)
            assert row is not None
            frozen = steps_action_identity(row)
        intent = await post_intent(
            client1, auth, task_id, frozen, lease_id, "evidence://q12-before"
        )
        assert intent.status_code == 201, intent.text

        # Network drops: the lease lapses with no further heartbeats.
        await expire_lease(app1, task_id)

        # The very same binding re-claims through the OTHER API process: the
        # committed intent keeps the task out of the dispatch loop (the claim
        # hits the RECONCILING blocking guard and answers 204 without ever
        # requeueing the task for a fresh dispatch).
        reclaimer = await claim(client2, auth)
        assert reclaimer.status_code == 204, reclaimer.text

        # External observables — identical from BOTH processes (shared DB):
        # one INTENT row, attempt 1, RECONCILING; the expired lease fields are
        # left in place precisely because the task was never requeued.
        for app in (app1, app2):
            row = await task_row(app, task_id)
            assert row.business_state == "RECONCILING"
            assert row.attempt == 1
            rows = await ledger_rows(app, task_id)
            assert [item.status for item in rows] == ["INTENT"]
        print(
            "\n[Q12/F1x] cross-process: claim 204, attempt=1, single INTENT row "
            "visible from both API processes"
        )


# ---------------------------------------------------------------------------
# F2: accessibility rebind (process re-registration vs transport refresh)
# ---------------------------------------------------------------------------


async def test_f2_accessibility_rebind_stale_envelope_then_identity_preserving_recovery(api):
    client, app = api
    device, auth = await provision(client, "f2-rebind")
    first = await register_fleet_session(app, auth, boot_id="q12-boot-f2")
    assert first["failedGates"] == []
    session_before = await active_fleet_session_id(app, device)

    task_id = await mint_steps_task(client, device, delist_steps(0), "f2-rebind")
    claimed = await claim(client, auth)
    assert claimed.status_code == 200, claimed.text
    old_lease = str(claimed.json()["leaseId"])
    epoch_before = claimed.json()["controlEpoch"]
    started = await heartbeat(client, auth, task_id, old_lease, step=1)
    assert started.status_code == 200, started.text

    # Page-reopen analog FIRST: a transport device heartbeat refreshes
    # presence but must NOT mint or revoke a fleet session (only a process
    # re-registration does) — the page-reopen half of the Q02-B distinction.
    transport = await client.post(
        "/companion/v2/devices/heartbeat",
        headers=auth,
        json={
            "companionVersion": "1.0.0",
            "accessibilityEnabled": True,
            "runnerState": "RUNNING",
        },
    )
    assert transport.status_code == 200, transport.text
    assert await active_fleet_session_id(app, device) == session_before
    still_fine = await heartbeat(client, auth, task_id, old_lease, step=1)
    assert still_fine.status_code == 200, still_fine.text

    # Accessibility rebind: the companion process re-registers — a fresh
    # sessionId revokes the old session; the mid-run lease goes stale.
    rebound = await register_fleet_session(app, auth, boot_id="q12-boot-f2")
    assert rebound["sessionId"] != session_before
    session_after = await active_fleet_session_id(app, device)
    assert session_after == rebound["sessionId"]
    late = await heartbeat(client, auth, task_id, old_lease, step=2)
    status, code = problem_code(late)
    assert (status, code) == (409, "AUTHORIZATION_ENVELOPE_STALE")
    # (The intent/outcome channels do NOT yet carry this envelope check —
    # recorded as DEFECT-Q12-1 and pinned by the strict-xfail test below.)

    # Recovery: the lease lapses, the same task is re-claimed under the NEW
    # session with the frozen steps identity byte-identical.
    identity_before = (await task_row(app, task_id)).steps[0]["payloadIdentity"]
    await expire_lease(app, task_id)
    reclaimed = await claim(client, auth)
    assert reclaimed.status_code == 200, reclaimed.text
    body = reclaimed.json()
    assert body["taskId"] == task_id
    assert body["attempt"] == 2
    assert body["leaseId"] != old_lease
    assert body["controlEpoch"] > epoch_before
    row = await task_row(app, task_id)
    assert row.steps[0]["fleetSessionId"] == session_after
    assert row.steps[0]["payloadIdentity"] == identity_before
    assert row.steps[0]["payloadIdentity"] == real_steps_payload_identity(row)

    # The recovered task runs to a reconciled settle: exactly ONE strike.
    resumed = await heartbeat(client, auth, task_id, str(body["leaseId"]), step=2)
    assert resumed.status_code == 200, resumed.text
    frozen = steps_action_identity(row)
    strike = await post_intent(
        client, auth, task_id, frozen, str(body["leaseId"]), "evidence://q12-before"
    )
    assert strike.status_code == 201, strike.text
    outcome = await post_outcome(
        client,
        auth,
        task_id,
        frozen,
        str(body["leaseId"]),
        "APPLIED",
        "evidence://q12-after-strike",
    )
    assert outcome.status_code == 200, outcome.text
    confirmed = await control(
        client,
        task_id,
        "reconcile",
        {
            "decision": "CONFIRMED_APPLIED",
            "evidence": "fixture strike ledger shows the unique token applied",
            "platformItemId": "q12-fixture-token-1",
        },
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["state"] == "SUCCEEDED"
    rows = await ledger_rows(app, task_id)
    assert [item.status for item in rows] == ["APPLIED"]
    print(
        f"\n[Q12/F2] strikes={len(rows)} (exactly one), attempt=2 under session "
        f"{session_after[:12]}..., payloadIdentity unchanged"
    )


# DEFECT-Q12-1 fixed by A13 @a6a1cc8 (merge b2f488c): the gated
# commit channels now validate the fleet-session envelope.
async def test_f2_late_gated_intent_under_superseded_session_rejected(api):
    """Contract behavior for the DEFECT-Q12-1 channel: a gated intent posted
    under a lease whose session was superseded must be refused."""
    client, app = api
    device, auth = await provision(client, "f2-gap")
    await register_fleet_session(app, auth, boot_id="q12-boot-f2g")
    task_id = await mint_steps_task(client, device, delist_steps(0), "f2-gap")
    claimed = await claim(client, auth)
    assert claimed.status_code == 200, claimed.text
    old_lease = str(claimed.json()["leaseId"])
    started = await heartbeat(client, auth, task_id, old_lease, step=2)
    assert started.status_code == 200, started.text

    # Rebind: the fresh process registration revokes the minting session.
    await register_fleet_session(app, auth, boot_id="q12-boot-f2g")

    frozen = steps_action_identity(await task_row(app, task_id))
    late_intent = await post_intent(
        client, auth, task_id, frozen, old_lease, "evidence://q12-before"
    )
    status, code = problem_code(late_intent)
    assert (status, code) == (409, "AUTHORIZATION_ENVELOPE_STALE")
    assert await ledger_rows(app, task_id) == []  # nothing authorized post-rebind


# ---------------------------------------------------------------------------
# F3: cancel / recovery
# ---------------------------------------------------------------------------


async def test_f3_pause_manual_resume_recovery_keeps_identity(api):
    client, app = api
    ctx = await running_delist_task(client, app, "f3-resume", boot_id="q12-boot-f3r")
    task_id, lease = ctx["taskId"], ctx["leaseId"]

    paused = await control(client, task_id, "pause", {"reason": "manual handling"})
    assert paused.status_code == 200, paused.text
    acked = await control(client, task_id, "ack-paused", {"leaseId": lease})
    assert acked.status_code == 200, acked.text
    assert acked.json()["state"] == "PAUSED_WAITING_USER"

    before = await view_task(client, task_id)
    assert before["controlRevision"] == 2
    assert [event["event"] for event in before["controlEvents"]] == [
        "PAUSE_REQUESTED",
        "PAUSE_ACKED",
    ]

    resumed = await control(
        client, task_id, "resume", {"reason": "manual handling done", "pageVerified": True}
    )
    assert resumed.status_code == 200, resumed.text
    after = await view_task(client, task_id)
    assert after["state"] == "RESUME_CHECK"
    assert [event["revision"] for event in after["controlEvents"]] == [1, 2, 3]

    # The ORIGINAL task (not a re-mint) continues: resume supersedes the old
    # lease, so the companion heartbeats under the lease now on the row.
    row_after_resume = await task_row(app, task_id)
    resumed_lease = row_after_resume.lease_id
    assert resumed_lease is not None and resumed_lease != lease
    continued = await heartbeat(client, ctx["auth"], task_id, resumed_lease, step=3)
    assert continued.status_code == 200, continued.text
    assert continued.json()["businessState"] == "RUNNING"
    settled = await view_task(client, task_id)
    assert settled["taskId"] == task_id
    assert settled["attemptId"] == before["attemptId"]
    assert settled["commandPayload"] == before["commandPayload"]
    assert settled["snapshotSha256"] == before["snapshotSha256"]
    row = await task_row(app, task_id)
    assert row.steps[0]["payloadIdentity"] == real_steps_payload_identity(row)

    # Zero gated strikes during the whole manual-recovery cycle.
    assert await ledger_rows(app, task_id) == []
    done = await client.post(
        f"/companion/v2/tasks/{task_id}/complete",
        headers=ctx["auth"],
        json={"leaseId": resumed_lease, "result": {"outcome": "delisted"}},
    )
    assert done.status_code == 200, done.text
    final = await view_task(client, task_id)
    assert final["state"] == "SUCCEEDED"
    print(
        f"\n[Q12/F3-resume] controlRevision 1..3, strikes=0, attemptId "
        f"{settled['attemptId']} unchanged through pause/manual/resume"
    )


async def test_f3_cancel_running_converges_and_frees_device(api):
    client, app = api
    device, auth = await provision(client, "f3-cancel")
    await register_fleet_session(app, auth, boot_id="q12-boot-f3c")
    first_id = await mint_steps_task(client, device, delist_steps(0), "f3-cancel-1")
    second_id = await mint_steps_task(client, device, polish_steps(), "f3-cancel-2")

    claimed = await claim(client, auth)
    assert claimed.status_code == 200 and claimed.json()["taskId"] == first_id
    lease_id = str(claimed.json()["leaseId"])
    started = await heartbeat(client, auth, first_id, lease_id, step=1)
    assert started.status_code == 200, started.text

    cancel = await control(client, first_id, "cancel", {"reason": "operator abort"})
    assert cancel.status_code == 200, cancel.text
    assert cancel.json()["state"] == "CANCEL_REQUESTED"
    assert cancel.json()["controlEvents"][-1]["event"] == "CANCEL_REQUESTED"

    # The companion honors the request at its next safe point (fail path).
    honored = await client.post(
        f"/companion/v2/tasks/{first_id}/fail",
        headers=auth,
        json={"leaseId": lease_id, "errorCode": "CANCELLED", "detail": "operator abort"},
    )
    assert honored.status_code == 200, honored.text
    row = await task_row(app, first_id)
    assert row.status == "FAILED"
    assert row.error_code == "CANCELLED"

    # The device is freed immediately: no queue-head zombie, zero strikes.
    assert await ledger_rows(app, first_id) == []
    lease = await live_lease(app, device)
    assert lease is not None and lease.canceled_at is not None
    nxt = await claim(client, auth)
    assert nxt.status_code == 200, nxt.text
    assert nxt.json()["taskId"] == second_id
    print(
        f"\n[Q12/F3-cancel] CANCEL_REQUESTED->FAILED(CANCELLED), strikes=0, "
        f"next task {second_id[:8]}... claimed at once"
    )


async def test_f3_cancel_refused_while_unknown_open_and_keep_waiting_blocks_reclaim(api):
    client, app = api
    ctx = await running_delist_task(client, app, "f3-unknown", boot_id="q12-boot-f3u")
    task_id, lease, frozen = ctx["taskId"], ctx["leaseId"], ctx["frozen"]

    intent = await post_intent(client, ctx["auth"], task_id, frozen, lease, "evidence://q12-before")
    assert intent.status_code == 201, intent.text
    outcome = await post_outcome(
        client, ctx["auth"], task_id, frozen, lease, "UNKNOWN", "evidence://q12-lost"
    )
    assert outcome.status_code == 200, outcome.text

    # fleet-identity/v1 §8: cancel never erases an open UNKNOWN.
    denied = await control(client, task_id, "cancel", {"reason": "operator wants out"})
    assert denied.status_code == 409, denied.text
    assert "reconcil" in denied.json()["detail"].lower()

    # KEEP_WAITING keeps the pending action and keeps the device blocked.
    waiting = await control(
        client,
        task_id,
        "reconcile",
        {"decision": "KEEP_WAITING", "evidence": "verifying the fixture strike"},
    )
    assert waiting.status_code == 200, waiting.text
    assert waiting.json()["state"] == "RECONCILING"
    rows = await ledger_rows(app, task_id)
    assert [item.status for item in rows] == ["UNKNOWN"]
    assert all(item.resolved_at is None for item in rows)
    blocked = await claim(client, ctx["auth"])
    status, code = problem_code(blocked)
    assert (status, code) == (409, "RECONCILE_REQUIRED")
    print(
        f"\n[Q12/F3-unknown] cancel 409 reconcile-first, UNKNOWN preserved "
        f"(resolved_at NULL), claim {status} {code}"
    )


# ---------------------------------------------------------------------------
# F4: old lease
# ---------------------------------------------------------------------------


async def test_f4_old_lease_rejected_on_every_companion_channel_after_reclaim(api):
    client, app = api
    device, auth = await provision(client, "f4-oldlease")
    await register_fleet_session(app, auth, boot_id="q12-boot-f4")
    task_id = await mint_steps_task(client, device, delist_steps(0), "f4-oldlease")

    first = await claim(client, auth)
    assert first.status_code == 200, first.text
    old_lease = str(first.json()["leaseId"])
    old_epoch = first.json()["controlEpoch"]
    started = await heartbeat(client, auth, task_id, old_lease, step=1)
    assert started.status_code == 200, started.text

    # Disconnect + recovery: the same task re-claims with a fresh lease.
    await expire_lease(app, task_id)
    second = await claim(client, auth)
    assert second.status_code == 200, second.text
    body = second.json()
    assert body["taskId"] == task_id
    assert body["attempt"] == 2
    new_lease = str(body["leaseId"])
    assert new_lease != old_lease
    assert body["controlEpoch"] > old_epoch

    # Still PREFLIGHT here: release under the OLD lease is refused.
    stale_release = await client.post(
        f"/companion/v2/tasks/{task_id}/release",
        headers=auth,
        json={"leaseId": old_lease, "reason": "ACCESSIBILITY_NOT_ACTIVE"},
    )
    assert stale_release.status_code == 409, stale_release.text

    resumed = await heartbeat(client, auth, task_id, new_lease, step=1)
    assert resumed.status_code == 200, resumed.text

    # Every remaining companion channel under the old lease is rejected.
    stale_heartbeat = await heartbeat(client, auth, task_id, old_lease, step=2)
    assert stale_heartbeat.status_code == 409, stale_heartbeat.text
    stale_event = await client.post(
        f"/companion/v2/tasks/{task_id}/events",
        headers=auth,
        json={
            "leaseId": old_lease,
            "sequence": 1,
            "eventType": "STEP_STARTED",
            "stepIndex": 1,
            "payload": {"stepId": "open-card-menu"},
        },
    )
    assert stale_event.status_code == 409, stale_event.text
    stale_complete = await client.post(
        f"/companion/v2/tasks/{task_id}/complete",
        headers=auth,
        json={"leaseId": old_lease, "result": {"outcome": "stolen"}},
    )
    assert stale_complete.status_code == 409, stale_complete.text
    frozen = steps_action_identity(await task_row(app, task_id))
    stale_intent = await post_intent(
        client, auth, task_id, frozen, old_lease, "evidence://q12-before"
    )
    assert stale_intent.status_code == 409, stale_intent.text

    # Exactly one live lease; the gated strike happens at most once.
    lease = await live_lease(app, device)
    assert lease is not None and lease.lease_id == new_lease
    print(
        f"\n[Q12/F4] old lease rejected on release/heartbeat/events/complete/"
        f"intent (409x5), attempt=2, controlEpoch {old_epoch}->{body['controlEpoch']}"
    )


async def test_f4_committed_intent_survives_lease_loss_without_second_dispatch(api):
    client, app = api
    ctx = await running_delist_task(client, app, "f4-intent", boot_id="q12-boot-f4i")
    task_id, lease, frozen = ctx["taskId"], ctx["leaseId"], ctx["frozen"]

    authorized = await post_intent(
        client, ctx["auth"], task_id, frozen, lease, "evidence://q12-before"
    )
    assert authorized.status_code == 201, authorized.text

    # Partition: the lease lapses before any outcome/finish ACK.
    await expire_lease(app, task_id)
    reclaimer = await claim(client, ctx["auth"])
    assert reclaimer.status_code == 204, reclaimer.text
    row = await task_row(app, task_id)
    assert row.business_state == "RECONCILING"
    assert row.attempt == 1  # never re-dispatched as fresh work

    # No lease can complete the strike: the old one is gone and no new one
    # was issued — the committed action stays exactly-once, forever pending
    # operator reconciliation.
    late_old = await post_outcome(
        client, ctx["auth"], task_id, frozen, lease, "APPLIED", "evidence://q12-after"
    )
    assert late_old.status_code == 409, late_old.text
    fabricated = await post_outcome(
        client,
        ctx["auth"],
        task_id,
        frozen,
        "not-the-issued-lease",
        "APPLIED",
        "evidence://q12-after",
    )
    assert fabricated.status_code == 409, fabricated.text
    rows = await ledger_rows(app, task_id)
    assert [item.status for item in rows] == ["INTENT"]
    assert await audit_actions(app, frozen["action_key"]) == ["mobile.action.intent"]

    # The drift-hardening projection: even a corrupted QUEUED row cannot make
    # claim re-dispatch the committed task (KEEP_WAITING — 204, no dispatch).
    async with app.state.database.unit_of_work() as session:
        current = await session.get(MobileTaskRow, task_id)
        assert current is not None
        current.status = "QUEUED"
        current.business_state = "QUEUED"
        current.lease_id = None
    drifted = await claim(client, ctx["auth"])
    assert drifted.status_code == 204, drifted.text
    row = await task_row(app, task_id)
    assert row.business_state == "RECONCILING"
    assert [item.status for item in await ledger_rows(app, task_id)] == ["INTENT"]
    print(
        "\n[Q12/F4i] committed intent: claim 204 (and drift-corruption still "
        "204), single INTENT row, attempt=1 — operator reconciliation is the "
        "only exit"
    )


# ---------------------------------------------------------------------------
# F5: input focus preemption
# ---------------------------------------------------------------------------


async def test_f5_ime_gate_blocks_dispatch_until_input_ready(api):
    client, app = api
    device, auth = await provision(client, "f5-ime")
    # IME preempted at registration: the closed capability table is
    # negotiated but the ime executable gate fails.
    gated = await register_fleet_session(app, auth, boot_id="q12-boot-f5", ime_ready=False)
    assert gated["executable"] is False
    assert gated["failedGates"] == ["ime"]

    task_id = await mint_steps_task(client, device, delist_steps(0), "f5-ime")
    blocked = await claim(client, auth)
    assert blocked.status_code == 204, blocked.text
    row = await task_row(app, task_id)
    assert row.status == "QUEUED"  # not dispatched, not failed
    assert await ledger_rows(app, task_id) == []

    # Input restored (process re-registration with ime ready): dispatch opens.
    restored = await register_fleet_session(app, auth, boot_id="q12-boot-f5")
    assert restored["executable"] is True
    assert restored["failedGates"] == []
    dispatched = await claim(client, auth)
    assert dispatched.status_code == 200, dispatched.text
    assert dispatched.json()["taskId"] == task_id
    print(
        f"\n[Q12/F5-ime] failedGates ['ime'] -> claim 204 (QUEUED, 0 strikes); "
        f"restored -> claim 200 task {task_id[:8]}..."
    )


async def test_f5_midrun_focus_preemption_fails_closed_with_zero_strikes(api):
    client, app = api
    device, auth = await provision(client, "f5-focus")
    await register_fleet_session(app, auth, boot_id="q12-boot-f5f")
    preempted_id = await mint_steps_task(client, device, delist_steps(0), "f5-focus-1")
    next_id = await mint_steps_task(client, device, polish_steps(), "f5-focus-2")

    claimed = await claim(client, auth)
    assert claimed.status_code == 200 and claimed.json()["taskId"] == preempted_id
    lease_id = str(claimed.json()["leaseId"])
    started = await heartbeat(client, auth, preempted_id, lease_id, step=1)
    assert started.status_code == 200, started.text

    # Focus stolen mid-input (acceptance-target focus_thief analog): the
    # companion terminates fail-closed — it must NOT limp into the gated
    # confirm (ui-observation/v1 §4 InputProof: inconclusive input fails).
    preempted = await client.post(
        f"/companion/v2/tasks/{preempted_id}/fail",
        headers=auth,
        json={
            "leaseId": lease_id,
            "errorCode": "INPUT_FOCUS_PREEMPTED",
            "detail": "input_field lost IME focus mid-step; InputProof inconclusive",
        },
    )
    assert preempted.status_code == 200, preempted.text
    row = await task_row(app, preempted_id)
    assert row.status == "FAILED"
    assert row.error_code == "INPUT_FOCUS_PREEMPTED"

    # External observables: ZERO gated strikes, device freed, queue moves on.
    assert await ledger_rows(app, preempted_id) == []
    lease = await live_lease(app, device)
    assert lease is not None and lease.canceled_at is not None
    nxt = await claim(client, auth)
    assert nxt.status_code == 200, nxt.text
    assert nxt.json()["taskId"] == next_id
    print(
        f"\n[Q12/F5-focus] INPUT_FOCUS_PREEMPTED -> FAILED, strikes=0, next "
        f"task {next_id[:8]}... dispatched"
    )


# ---------------------------------------------------------------------------
# Accounting: software results vs device-pending items (separate counts)
# ---------------------------------------------------------------------------


async def test_q12_software_and_device_item_accounting() -> None:
    """Explicit separate counts of software results and device-side items."""
    assert len(SOFTWARE_TEST_NAMES) == 13
    assert set(SOFTWARE_SCENARIOS) == {
        "F1-intent-ack-loss",
        "F1-partition-no-redispatch",
        "F2-accessibility-rebind",
        "F3-pause-manual-resume",
        "F3-cancel-running-convergence",
        "F3-cancel-unknown-preserved",
        "F4-old-lease-channels",
        "F4-committed-intent-no-redispatch",
        "F5-ime-gate",
        "F5-focus-preemption-fail-closed",
    }
    print(f"\n[Q12 accounting] software result items: {len(SOFTWARE_TEST_NAMES)}")
    print(
        "[Q12 accounting] note: test_f2_late_gated_intent_under_superseded_"
        "session_rejected is the strict xfail pinning DEFECT-Q12-1"
    )
    for name in SOFTWARE_TEST_NAMES:
        print(f"[Q12 software] {name}")
    print(f"[Q12 accounting] device-pending items: {len(DEVICE_PENDING_ITEMS)}")
    for item in DEVICE_PENDING_ITEMS:
        print(f"[Q12 device-pending] {item['id']} — {item['aspect']} ({item['owner']})")
    assert len(DEVICE_PENDING_ITEMS) == 4


# ---------------------------------------------------------------------------
# On-device items (Q13 hardware line) — skipped, counted separately
# ---------------------------------------------------------------------------


@pytest.mark.skip(
    reason="device-item q12-device-process-restart-not-page-reopen: needs a real "
    "controlled device; the acceptance-target boot_marker (BOOT# process_boots "
    "vs PAGE# page_opens) is the anti-hollow-pass fixture — a run without a "
    "BOOT# increment is a page reopen and must NOT count as restart recovery "
    "(Q02-B1 lesson)"
)
async def test_device_item_process_restart_distinguish_boot_marker(api) -> None:
    raise AssertionError("never runs: hardware-only")


@pytest.mark.skip(
    reason="device-item q12-device-accessibility-rebind: needs the real companion "
    "process to re-register while a lease is live (accessibility off/on); the "
    "API-side projection (stale envelope + identity-preserving recovery) is "
    "covered by test_f2_accessibility_rebind_stale_envelope_then_identity_"
    "preserving_recovery at this SHA"
)
async def test_device_item_accessibility_rebind_on_device(api) -> None:
    raise AssertionError("never runs: hardware-only")


@pytest.mark.skip(
    reason="device-item q12-device-ime-focus-preemption: needs a real IME and the "
    "acceptance-target focus_thief_button stealing input_field focus; external "
    "observable is the app execution_ledger FOCUS_LOSS counter; the fail-closed "
    "projection (zero ledger strikes) is covered by "
    "test_f5_midrun_focus_preemption_fails_closed_with_zero_strikes"
)
async def test_device_item_ime_focus_preemption_on_device(api) -> None:
    raise AssertionError("never runs: hardware-only")


@pytest.mark.skip(
    reason="device-item q12-device-unique-target-confirm-strike: gated confirm on "
    "the acceptance-target unique-token card (arm_button -> TARGET_TOKEN -> "
    "confirm dialog) replaces the real-shop cardIndex=0 targeting; requires the "
    "controller to allowlist com.company.cloudctl.testtarget in the companion "
    "locator registry before the companion can execute it on hardware"
)
async def test_device_item_unique_target_confirm_strike_on_device(api) -> None:
    raise AssertionError("never runs: hardware-only")
