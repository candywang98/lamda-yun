"""A13 controlled-action recovery matrix (backend line).

Frozen bases: p09-ledger/20260910.1 + p09-reconcile/20260910.1 +
fleet-identity/v1@20260916.1 (§2 account debt, §4 stable identity vs dynamic
envelope, §8 reclaim guards). The matrix covers:

- six-family stable-identity goldens (incl. the cross-language
  steps-identity-golden.json parity) and the §4 envelope-field guard
  (negative-fixture mirror);
- the pure p09 outcome guard (verbatim 409 order/messages), the monotonic
  ledger phase machine, and the platform-result proof conjunction;
- crash injection around the intent commit (rollback → retry exactly once),
  intent replay semantics, dispatch-window re-authorization refusal, §8
  post-commit reclaim blocking, outcome idempotency and terminal no-regress;
- DEFECT-Q12-1: the gated intent/outcome channels honor the fleet session
  envelope (late gated intent/outcome under a superseded session/boot with a
  still-live lease → 409 AUTHORIZATION_ENVELOPE_STALE, §4 pre-commit
  recovery), mirroring the heartbeat-channel guard;
- the platform_account_id ledger column (probe records it, steps stay NULL,
  legacy NULL rows still replay) and audit evidence bindings;
- migration 20260916_0024 round-trip and real-PostgreSQL cross-connection
  commit visibility (SQLite cannot stand in for that proof).
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from cloudctl_api import mobile_actions
from cloudctl_api.controlled_actions import (
    ACTION_PHASE_INTENT,
    ACTION_PHASE_ORDER,
    ACTION_PHASE_REPORTED,
    ACTION_PHASE_RESOLVED,
    OUTCOME_APPLY,
    OUTCOME_REPLAY,
    STABLE_IDENTITY_GOLDENS,
    action_phase,
    evidence_binding,
    identity_inputs_free_of_envelope,
    outcome_guard,
    phase_transition_allowed,
    platform_result_proven,
)
from cloudctl_api.db import (
    AuditEventRow,
    Database,
    MobileActionCommitRow,
    MobileTaskRow,
)
from cloudctl_api.fleet_identity import AUTHORIZATION_ENVELOPE_FIELDS
from cloudctl_api.mobile_actions import action_identity, canonical_steps, steps_action_identity
from cloudctl_domain import ConflictError
from sqlalchemy import select
from test_p09_action_ledger import paths, running
from test_p14_recipe_versions import (  # noqa: F401 - pytest fixture injection
    api,
    isolated_postgres,  # noqa: F401 - fixture graph for the postgres api param
    pg_url,  # noqa: F401 - fixture graph for the postgres api param
)
from test_platform_tasks import identity
from test_xianyu_maintenance import _create_steps_task, delist_steps

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = REPOSITORY_ROOT / "services" / "control-api" / "alembic.ini"
CROSS_LANGUAGE_GOLDEN = (
    REPOSITORY_ROOT / "mobile/companion/app/src/test/resources/steps-identity-golden.json"
)
ENVELOPE_NEGATIVE_FIXTURE = (
    REPOSITORY_ROOT / "contracts/fleet/v1/fixtures/k10-negative-actionkey-contains-epoch.json"
)

IDENTITY_INPUT_KEYS = (
    "taskId",
    "commandType",
    "accountId",
    "bindingVersion",
    "snapshotSha256",
    "recipeSha256",
    "actionId",
)


async def _audit_rows(app, action_key: str, kind: str) -> list[AuditEventRow]:
    async with app.state.database.unit_of_work() as session:
        return list(
            await session.scalars(
                select(AuditEventRow).where(
                    AuditEventRow.action == f"mobile.action.{kind}",
                    AuditEventRow.resource_id == action_key,
                )
            )
        )


async def _ledger_row(app, action_key: str) -> MobileActionCommitRow | None:
    async with app.state.database.unit_of_work() as session:
        return await session.get(MobileActionCommitRow, action_key)


def _phase_row(status: str, revision: int, **overrides) -> MobileActionCommitRow:
    base = dict(
        action_key="a" * 64,
        tenant_id="00000000-0000-7000-8000-000000000111",
        task_id="00000000-0000-7000-8000-000000000222",
        device_id="00000000-0000-7000-8000-000000000333",
        account_id="00000000-0000-7000-8000-000000000333",
        binding_version=0,
        recipe_version_id="steps",
        recipe_sha256="b" * 64,
        snapshot_sha256="b" * 64,
        action_id="click-publish",
        parameter_hash="c" * 64,
        lease_id="lease-a13",
        status=status,
        before_evidence="evidence://before",
        resolution_revision=revision,
        created_at=datetime(2026, 9, 16, tzinfo=UTC),
        updated_at=datetime(2026, 9, 16, tzinfo=UTC),
    )
    base.update(overrides)
    return MobileActionCommitRow(**base)


# ---------------------------------------------------------------------------
# Six-family stable identity goldens + §4 envelope invariance
# ---------------------------------------------------------------------------


def test_stable_identity_goldens_recompute_from_the_frozen_formula():
    """Every family vector must reproduce through action_identity unchanged."""

    assert set(STABLE_IDENTITY_GOLDENS) == {
        "probe",
        "xianyu-steps",
        "xhs",
        "douyin",
        "maintenance-v1",
        "maintenance-v2",
    }
    for family, vector in STABLE_IDENTITY_GOLDENS.items():
        key, parameters = action_identity(
            *(
                vector[name]
                for name in (
                    "taskId",
                    "commandType",
                    "accountId",
                    "bindingVersion",
                    "snapshotSha256",
                    "recipeSha256",
                    "actionId",
                )
            )
        )
        assert key == vector["actionKey"], family
        assert parameters == vector["parameterHash"], family


def test_xianyu_steps_golden_is_the_cross_language_golden():
    """Parity with steps-identity-golden.json (ControlledStepsIdentityTest)."""

    golden = json.loads(CROSS_LANGUAGE_GOLDEN.read_text())
    vector = STABLE_IDENTITY_GOLDENS["xianyu-steps"]
    assert vector["taskId"] == golden["taskId"]
    assert vector["accountId"] == golden["deviceId"]  # recorded §2 debt
    assert vector["bindingVersion"] == golden["bindingVersion"]
    assert vector["snapshotSha256"] == vector["recipeSha256"] == golden["stepsSha256"]
    assert vector["actionKey"] == golden["actionKey"]
    assert vector["parameterHash"] == golden["parameterHash"]
    # canonical_steps itself must still reproduce the frozen steps digest.
    digest = __import__("hashlib").sha256(canonical_steps(golden["steps"]).encode()).hexdigest()
    assert digest == golden["stepsSha256"]


def test_identity_inputs_free_of_envelope_guard_mirrors_the_negative_fixture():
    # The six golden input sets are clean: no envelope field ever enters them.
    for family, vector in STABLE_IDENTITY_GOLDENS.items():
        inputs = {key: vector[key] for key in IDENTITY_INPUT_KEYS}
        assert identity_inputs_free_of_envelope(inputs) == [], family

    # Negative fixture mirror (k10-negative-actionkey-contains-epoch.json).
    fixture = json.loads(ENVELOPE_NEGATIVE_FIXTURE.read_text())
    assert fixture["expect"] == "REJECT"
    violations = identity_inputs_free_of_envelope(fixture["identityInputs"])
    assert "controlEpoch" in violations
    assert set(violations) == {"controlEpoch", "fencingToken", "sessionId"}

    # Closed mirror: every dynamic envelope field is flagged, nothing else.
    polluted = {name: "x" for name in AUTHORIZATION_ENVELOPE_FIELDS}
    assert identity_inputs_free_of_envelope(polluted) == list(AUTHORIZATION_ENVELOPE_FIELDS)
    assert identity_inputs_free_of_envelope({"taskId": "t"}) == []


# ---------------------------------------------------------------------------
# Pure p09 outcome guard (order and 409 messages frozen verbatim)
# ---------------------------------------------------------------------------


def test_outcome_guard_check_order_and_verbatim_messages():
    base = dict(
        row_status="INTENT",
        row_parameter_hash="c" * 64,
        row_lease_id="lease-a13",
        row_reported_evidence=None,
        row_resolution_revision=0,
        row_before_evidence="evidence://before",
        task_business_state="RECONCILING",
        body_parameter_hash="c" * 64,
        body_lease_id="lease-a13",
        body_status="APPLIED",
        body_evidence="evidence://after",
    )

    def guard(**overrides) -> str:
        return outcome_guard(**{**base, **overrides})

    # 1. identity mismatch first — even when the row is already resolved.
    with pytest.raises(ConflictError, match="outcome identity mismatch"):
        guard(body_parameter_hash="0" * 64, row_resolution_revision=1)
    with pytest.raises(ConflictError, match="outcome identity mismatch"):
        guard(body_lease_id="other-lease")

    # 2. resolved rows / non-RECONCILING tasks are immutable.
    with pytest.raises(ConflictError, match="action already resolved or task not reconciling"):
        guard(row_resolution_revision=1)
    with pytest.raises(ConflictError, match="action already resolved or task not reconciling"):
        guard(task_business_state="RUNNING")

    # 3. already-reported rows: replay equality only.
    with pytest.raises(ConflictError, match="outcome replay differs"):
        guard(
            row_status="UNKNOWN",
            body_status="UNKNOWN",
            row_reported_evidence="x",
            body_evidence="y",
        )
    assert (
        guard(
            row_status="UNKNOWN",
            row_reported_evidence="evidence://lost",
            body_status="UNKNOWN",
            body_evidence="evidence://lost",
        )
        == OUTCOME_REPLAY
    )

    # 4. first APPLIED report needs independent postcondition evidence.
    with pytest.raises(ConflictError, match="independent postcondition evidence required"):
        guard(body_evidence="evidence://before")
    assert guard() == OUTCOME_APPLY
    # UNKNOWN reports are not postcondition-bound.
    assert guard(body_status="UNKNOWN", body_evidence="evidence://before") == OUTCOME_APPLY


# ---------------------------------------------------------------------------
# Monotonic phase machine + platform-result proof (pure)
# ---------------------------------------------------------------------------


def test_action_phase_machine_is_monotonic():
    assert action_phase(_phase_row("INTENT", 0)) == ACTION_PHASE_INTENT
    assert action_phase(_phase_row("APPLIED", 0)) == ACTION_PHASE_REPORTED
    assert action_phase(_phase_row("UNKNOWN", 0)) == ACTION_PHASE_REPORTED
    assert action_phase(_phase_row("APPLIED", 1)) == ACTION_PHASE_RESOLVED
    assert action_phase(_phase_row("NOT_SUBMITTED", 2)) == ACTION_PHASE_RESOLVED

    for current in ACTION_PHASE_ORDER:
        assert phase_transition_allowed(current, current)
        for target in ACTION_PHASE_ORDER:
            assert phase_transition_allowed(current, target) == (
                ACTION_PHASE_ORDER.index(target) >= ACTION_PHASE_ORDER.index(current)
            )
    # The two hard guarantees: reporting never re-opens intent, and a
    # resolution can never regress to a live phase.
    assert not phase_transition_allowed(ACTION_PHASE_REPORTED, ACTION_PHASE_INTENT)
    assert not phase_transition_allowed(ACTION_PHASE_RESOLVED, ACTION_PHASE_INTENT)
    assert not phase_transition_allowed(ACTION_PHASE_RESOLVED, ACTION_PHASE_REPORTED)


def test_platform_result_proven_requires_the_full_closure_conjunction():
    resolved_at = datetime(2026, 9, 16, 12, tzinfo=UTC)
    closed = _phase_row(
        "APPLIED", 1, resolution_evidence="operator verified", resolved_at=resolved_at
    )
    assert platform_result_proven(closed)
    assert platform_result_proven(
        _phase_row("NOT_SUBMITTED", 3, resolution_evidence="never landed", resolved_at=resolved_at)
    )
    # Every missing closure leg keeps the row unproven.
    assert not platform_result_proven(_phase_row("INTENT", 0))  # never reported
    assert not platform_result_proven(_phase_row("APPLIED", 0))  # reported, unresolved
    assert not platform_result_proven(_phase_row("UNKNOWN", 0))  # open uncertainty
    assert not platform_result_proven(_phase_row("APPLIED", 1, resolution_evidence="x"))  # no time
    assert not platform_result_proven(
        _phase_row("APPLIED", 1, resolution_evidence="", resolved_at=resolved_at)  # no evidence
    )
    assert not platform_result_proven(
        _phase_row("UNKNOWN", 1, resolution_evidence="x", resolved_at=resolved_at)  # non-terminal
    )


def test_evidence_binding_is_row_local_and_json_safe():
    row = _phase_row(
        "APPLIED",
        1,
        platform_account_id="00000000-0000-7000-8000-000000000999",
        resolution_evidence="operator verified",
        resolved_at=datetime(2026, 9, 16, 12, tzinfo=UTC),
    )
    binding = evidence_binding(row)
    assert binding["taskId"] == row.task_id
    assert binding["deviceId"] == row.device_id
    assert binding["accountId"] == "00000000-0000-7000-8000-000000000999"
    assert binding["accountSource"] == "platform_account_id"
    assert binding["leaseId"] == row.lease_id
    assert binding["bindingVersion"] == row.binding_version
    assert binding["recipeSha256"] == row.recipe_sha256
    assert binding["createdAt"] == "2026-09-16T00:00:00+00:00"
    assert binding["resolvedAt"] == "2026-09-16T12:00:00+00:00"
    # JSON-safe (audit metadata goes through a JSON column).
    assert json.loads(json.dumps(binding)) == binding
    # Legacy rows (platform account unknown) fall back to the account column.
    legacy = evidence_binding(_phase_row("INTENT", 0))
    assert legacy["accountId"] == _phase_row("INTENT", 0).account_id
    assert legacy["accountSource"] == "legacy_account_id"


# ---------------------------------------------------------------------------
# Crash injection around the intent commit
# ---------------------------------------------------------------------------


async def test_crash_before_intent_commit_rolls_back_and_retries_exactly_once(api, monkeypatch):  # noqa: F811
    """A crash inside the intent UoW leaves nothing behind; the retry
    authorizes exactly once and writes exactly one audit row."""

    client, app = api
    task, auth, body = await running(api)
    intent, action = paths(task, body)

    real_audit = mobile_actions.audit_action
    calls: list[str] = []

    def crashing_audit(session, row, actor_id, kind):
        calls.append(kind)
        if len(calls) == 1:
            raise RuntimeError("simulated crash before intent commit")
        return real_audit(session, row, actor_id, kind)

    monkeypatch.setattr(mobile_actions, "audit_action", crashing_audit)
    with pytest.raises(RuntimeError, match="simulated crash before intent commit"):
        await client.post(intent, headers=auth, json=body)
    monkeypatch.undo()

    # The rollback left no half-written ledger row, no audit, no state move.
    assert await _ledger_row(app, body["actionKey"]) is None
    async with app.state.database.unit_of_work() as session:
        task_row = await session.get(MobileTaskRow, task)
        assert task_row.business_state == "RUNNING"
        assert (
            await session.scalar(
                select(AuditEventRow).where(AuditEventRow.resource_id == body["actionKey"])
            )
            is None
        )

    first = await client.post(intent, headers=auth, json=body)
    assert first.status_code == 201, first.text
    assert first.json()["decision"] == "AUTHORIZED"
    replay = await client.post(intent, headers=auth, json=body)
    assert replay.status_code == 200
    assert replay.json()["decision"] == "RECONCILE_REQUIRED"
    rows = await _audit_rows(app, body["actionKey"], "intent")
    assert len(rows) == 1  # exactly one authorization despite the crash-retry


# ---------------------------------------------------------------------------
# Intent replay / dispatch window / repeated-event audit counts
# ---------------------------------------------------------------------------


async def test_intent_replay_reconcile_required_and_audit_counts(api):  # noqa: F811
    client, app = api
    task, auth, body = await running(api)
    intent, action = paths(task, body)

    first = await client.post(intent, headers=auth, json=body)
    assert first.status_code == 201, first.text
    view = first.json()["action"]
    for _ in range(3):
        replay = await client.post(intent, headers=auth, json=body)
        assert replay.status_code == 200
        assert replay.json()["decision"] == "RECONCILE_REQUIRED"
        assert replay.json()["action"] == view
    assert len(await _audit_rows(app, body["actionKey"], "intent")) == 1

    # Additive view field: the ledger now exposes the platform account.
    assert view["platformAccountId"] is not None

    report = dict(
        leaseId=body["leaseId"],
        parameterHash=body["parameterHash"],
        status="APPLIED",
        evidence="evidence://independent-after",
    )
    outcome = await client.post(action + "/outcome", headers=auth, json=report)
    assert outcome.status_code == 200, outcome.text
    duplicate = await client.post(action + "/outcome", headers=auth, json=report)
    assert duplicate.status_code == 200
    assert duplicate.json() == outcome.json()
    conflict = await client.post(
        action + "/outcome", headers=auth, json={**report, "evidence": "different"}
    )
    assert conflict.status_code == 409
    assert len(await _audit_rows(app, body["actionKey"], "outcome")) == 1


async def test_repeated_intent_after_dispatch_never_reauthorizes(api):  # noqa: F811
    """Once the dispatch window opened, no intent variant re-authorizes."""

    client, app = api
    task, auth, body = await running(api)
    intent, action = paths(task, body)
    assert (await client.post(intent, headers=auth, json=body)).status_code == 201
    async with app.state.database.unit_of_work() as session:
        assert (await session.get(MobileTaskRow, task)).business_state == "RECONCILING"

    # Same body → replay (200, never 201/AUTHORIZED again).
    assert (await client.post(intent, headers=auth, json=body)).status_code == 200
    # Same actionKey, different parameterHash → identity mismatch.
    assert (
        await client.post(intent, headers=auth, json={**body, "parameterHash": "0" * 64})
    ).status_code == 409
    # Different lease window → replay differs / lease rejection.
    assert (
        await client.post(intent, headers=auth, json={**body, "leaseId": "other-window"})
    ).status_code == 409
    # Different before-evidence → replay differs.
    assert (
        await client.post(intent, headers=auth, json={**body, "beforeEvidence": "changed"})
    ).status_code == 409
    assert len(await _audit_rows(app, body["actionKey"], "intent")) == 1


# ---------------------------------------------------------------------------
# §8 post-commit reclaim blocking (maintenance steps family)
# ---------------------------------------------------------------------------


_MaintenanceFlow = tuple[str, dict[str, str], dict[str, str], dict[str, object]]


async def _maintenance_running(api, name: str) -> _MaintenanceFlow:  # noqa: F811
    from test_platform_tasks import _enroll, create_direct_device

    client, app = api
    device = await create_direct_device(client, f"a13-{name}")
    created = await _create_steps_task(
        client, device, delist_steps(0), f"a13-{name}-{uuid.uuid4()}"
    )
    assert created.status_code == 201, created.text
    task = created.json()["taskId"]
    auth = await _enroll(client, device, f"a13-{name}-instance")
    claimed = await client.post(
        "/companion/v2/tasks/claim", headers=auth, json={"leaseSeconds": 60}
    )
    assert claimed.status_code == 200, claimed.text
    started = await client.post(
        f"/companion/v2/tasks/{task}/heartbeat",
        headers=auth,
        json={"leaseId": claimed.json()["leaseId"], "currentStep": 2},
    )
    assert started.status_code == 200, started.text
    async with app.state.database.unit_of_work() as session:
        frozen = steps_action_identity(await session.get(MobileTaskRow, task))
    body = dict(
        leaseId=claimed.json()["leaseId"],
        actionId=frozen["action_id"],
        actionKey=frozen["action_key"],
        parameterHash=frozen["parameter_hash"],
        beforeEvidence="evidence://a13-before",
    )
    return task, auth, body, frozen


async def test_post_commit_reclaim_hangs_reconciling_and_blocks_reexecution(api):  # noqa: F811
    """§8: after the gated commit the task is never re-dispatched as fresh
    work — claim parks it in RECONCILING via the ledger, and the old lease
    can no longer move anything."""

    client, app = api
    task, auth, body, _frozen = await _maintenance_running(api, "post-commit")
    intent, action = paths(task, body)
    assert (await client.post(intent, headers=auth, json=body)).status_code == 201

    # Crash: the lease lapses with no outcome/finish ACK.
    from datetime import timedelta

    async with app.state.database.unit_of_work() as session:
        row = await session.get(MobileTaskRow, task)
        row.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    reclaim = await client.post(
        "/companion/v2/tasks/claim", headers=auth, json={"leaseSeconds": 60}
    )
    assert reclaim.status_code == 204
    async with app.state.database.unit_of_work() as session:
        row = await session.get(MobileTaskRow, task)
        assert row.business_state == "RECONCILING"  # _post_commit_pending parked it
        assert row.attempt == 1
        ledger = await session.get(MobileActionCommitRow, body["actionKey"])
        assert ledger is not None and ledger.status == "INTENT"
        assert ledger.platform_account_id is None  # steps task carries no account

    # The dead lease cannot report a late outcome nor re-open the window.
    report = dict(
        leaseId=body["leaseId"],
        parameterHash=body["parameterHash"],
        status="APPLIED",
        evidence="evidence://late",
    )
    assert (await client.post(action + "/outcome", headers=auth, json=report)).status_code == 409
    assert (await client.post(intent, headers=auth, json=body)).status_code == 409


async def test_open_unknown_blocks_reclaim_with_reconcile_required(api):  # noqa: F811
    client, _app = api
    task, auth, body, _frozen = await _maintenance_running(api, "open-unknown")
    intent, action = paths(task, body)
    assert (await client.post(intent, headers=auth, json=body)).status_code == 201
    report = dict(
        leaseId=body["leaseId"],
        parameterHash=body["parameterHash"],
        status="UNKNOWN",
        evidence="evidence://lost",
    )
    outcome = await client.post(action + "/outcome", headers=auth, json=report)
    assert outcome.status_code == 200, outcome.text

    blocked = await client.post(
        "/companion/v2/tasks/claim", headers=auth, json={"leaseSeconds": 60}
    )
    assert blocked.status_code == 409
    assert blocked.headers["content-type"].startswith("application/problem+json")
    assert blocked.json()["code"] == "RECONCILE_REQUIRED"


# ---------------------------------------------------------------------------
# Terminal no-regress + platform account column + bindings
# ---------------------------------------------------------------------------


async def test_resolution_is_terminal_late_events_cannot_regress_the_row(api):  # noqa: F811
    client, app = api
    task, auth, body = await running(api)
    intent, action = paths(task, body)
    assert (await client.post(intent, headers=auth, json=body)).status_code == 201
    report = dict(
        leaseId=body["leaseId"],
        parameterHash=body["parameterHash"],
        status="APPLIED",
        evidence="evidence://independent-after",
    )
    assert (await client.post(action + "/outcome", headers=auth, json=report)).status_code == 200

    # Not proven until the operator resolution closes it.
    row = await _ledger_row(app, body["actionKey"])
    assert action_phase(row) == ACTION_PHASE_REPORTED
    assert not platform_result_proven(row)

    resolved = await client.post(
        f"/api/v1/platform-tasks/{task}:reconcile",
        headers=identity(),
        json={
            "decision": "CONFIRMED_APPLIED",
            "evidence": "operator observation",
            "platformItemId": "a13-probe-item-1",
        },
    )
    assert resolved.status_code == 200, resolved.text
    row = await _ledger_row(app, body["actionKey"])
    assert action_phase(row) == ACTION_PHASE_RESOLVED
    assert platform_result_proven(row)
    snapshot = {
        name: getattr(row, name)
        for name in ("status", "resolution_revision", "resolved_at", "resolution_evidence")
    }

    # Late events after resolution: both 409, row byte-identical.
    late_outcome = await client.post(action + "/outcome", headers=auth, json=report)
    assert late_outcome.status_code == 409
    late_intent = await client.post(intent, headers=auth, json=body)
    assert late_intent.status_code == 409
    row_after = await _ledger_row(app, body["actionKey"])
    assert {name: getattr(row_after, name) for name in snapshot} == snapshot


async def test_platform_account_column_replay_and_audit_binding(api):  # noqa: F811
    client, app = api
    task, auth, body = await running(api)
    intent, _action = paths(task, body)
    assert (await client.post(intent, headers=auth, json=body)).status_code == 201

    async with app.state.database.unit_of_work() as session:
        task_row = await session.get(MobileTaskRow, task)
        ledger = await session.get(MobileActionCommitRow, body["actionKey"])
        # Probe intent records the real platform account; the frozen identity
        # inputs (account_id column) stay untouched.
        assert ledger.platform_account_id == task_row.account_id
        assert ledger.account_id == task_row.account_id
        audit = (await _audit_rows(app, body["actionKey"], "intent"))[0]
        # Original audit keys kept, binding added.
        assert audit.metadata_json["taskId"] == task
        assert audit.metadata_json["actionKey"] == body["actionKey"]
        assert audit.metadata_json["status"] == "INTENT"
        binding = audit.metadata_json["evidenceBinding"]
        assert binding["accountId"] == task_row.account_id
        assert binding["accountSource"] == "platform_account_id"
        assert binding["leaseId"] == body["leaseId"]

        # Pre-migration row simulation: NULL platform_account_id must not
        # affect the immutable identity — replay stays RECONCILE_REQUIRED.
        ledger.platform_account_id = None

    replay = await client.post(intent, headers=auth, json=body)
    assert replay.status_code == 200
    assert replay.json()["decision"] == "RECONCILE_REQUIRED"


# ---------------------------------------------------------------------------
# DEFECT-Q12-1: session envelope guard on the gated intent/outcome channels
# ---------------------------------------------------------------------------


async def _gated_session_flow(api, name: str) -> tuple[str, dict[str, str], dict[str, str], str]:  # noqa: F811
    """Publish-steps (gated click) task claimed under a negotiated fleet
    session, so the claim stamps {fleetSessionId, fleetBootId} on the lease."""

    from test_fleet_identity import negotiate
    from test_p09_action_ledger import PUBLISH_STEPS
    from test_platform_tasks import _enroll, create_direct_device

    client, app = api
    device = await create_direct_device(client, f"a13-{name}")
    auth = await _enroll(client, device, f"a13-{name}-instance")
    token = auth["Authorization"].split(" ", 1)[1]
    created = await _create_steps_task(client, device, PUBLISH_STEPS, f"a13-{name}-{uuid.uuid4()}")
    assert created.status_code == 201, created.text
    task = created.json()["taskId"]
    await negotiate(app, token, boot_id=f"boot-{name}-one")
    claimed = await client.post(
        "/companion/v2/tasks/claim", headers=auth, json={"leaseSeconds": 60}
    )
    assert claimed.status_code == 200, claimed.text
    started = await client.post(
        f"/companion/v2/tasks/{task}/heartbeat",
        headers=auth,
        json={"leaseId": claimed.json()["leaseId"], "currentStep": 0},
    )
    assert started.status_code == 200, started.text
    async with app.state.database.unit_of_work() as session:
        row = await session.get(MobileTaskRow, task)
        frozen = steps_action_identity(row)
        header = dict(row.steps[0])
    # The claim must have stamped the dynamic envelope on this lease.
    assert header.get("fleetSessionId")
    assert header.get("fleetBootId") == f"boot-{name}-one"
    body = dict(
        leaseId=claimed.json()["leaseId"],
        actionId=frozen["action_id"],
        actionKey=frozen["action_key"],
        parameterHash=frozen["parameter_hash"],
        beforeEvidence="evidence://a13-envelope-before",
    )
    return task, auth, body, token


async def test_late_gated_intent_after_session_supersede_is_rejected(api):  # noqa: F811
    """DEFECT-Q12-1: after a re-registration (new bootId) the still-live lease
    must not authorize the gated click — 409 AUTHORIZATION_ENVELOPE_STALE."""

    client, app = api
    from test_fleet_identity import negotiate

    task, auth, body, token = await _gated_session_flow(api, "env-intent")
    intent, _action = paths(task, body)

    # The device re-registers (accessibility rebind / reboot): the old fleet
    # session is revoked while the AUTO lease stays unexpired.
    await negotiate(app, token, boot_id="boot-env-intent-two")

    late = await client.post(intent, headers=auth, json=body)
    assert late.status_code == 409, late.text
    assert late.headers["content-type"].startswith("application/problem+json")
    assert late.json()["code"] == "AUTHORIZATION_ENVELOPE_STALE"
    # No ledger row, no state move — the authorization never happened.
    assert await _ledger_row(app, body["actionKey"]) is None
    async with app.state.database.unit_of_work() as session:
        row = await session.get(MobileTaskRow, task)
        assert row.business_state == "RUNNING"


async def test_late_gated_outcome_after_session_supersede_is_rejected(api):  # noqa: F811
    """DEFECT-Q12-1 on the outcome channel, with the fresh-session control:
    the live session authorizes the intent normally; only the superseded
    envelope is refused."""

    client, app = api
    from test_fleet_identity import negotiate

    task, auth, body, token = await _gated_session_flow(api, "env-outcome")
    intent, action = paths(task, body)

    # Control: under the *current* session the guarded channels pass.
    fresh = await client.post(intent, headers=auth, json=body)
    assert fresh.status_code == 201, fresh.text

    await negotiate(app, token, boot_id="boot-env-outcome-two")
    report = dict(
        leaseId=body["leaseId"],
        parameterHash=body["parameterHash"],
        status="APPLIED",
        evidence="sha256:" + "e" * 64,
    )
    late_outcome = await client.post(action + "/outcome", headers=auth, json=report)
    assert late_outcome.status_code == 409, late_outcome.text
    assert late_outcome.json()["code"] == "AUTHORIZATION_ENVELOPE_STALE"
    row = await _ledger_row(app, body["actionKey"])
    assert row is not None and row.status == "INTENT"  # outcome never landed
    assert len(await _audit_rows(app, body["actionKey"], "outcome")) == 0

    # A late intent replay under the stale envelope is refused as well.
    late_replay = await client.post(intent, headers=auth, json=body)
    assert late_replay.status_code == 409
    assert late_replay.json()["code"] == "AUTHORIZATION_ENVELOPE_STALE"


# ---------------------------------------------------------------------------
# Migration 20260916_0024 round-trip
# ---------------------------------------------------------------------------


def test_mobile_action_platform_account_id_updown_is_symmetric(tmp_path: Path) -> None:
    """20260916_0024 (A13): nullable platform_account_id, reversible; legacy
    rows keep NULL and survive the down/up cycle."""

    database_path = tmp_path / "a13-platform-account-migrations.db"
    config = Config(ALEMBIC_INI)
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{database_path}")
    command.upgrade(config, "20260916_0023")

    legacy_key = "1" * 64
    with sqlite3.connect(database_path) as connection:
        columns = {
            str(row[1]) for row in connection.execute("PRAGMA table_info(mobile_action_commit)")
        }
        assert "platform_account_id" not in columns
        connection.execute(
            """
            INSERT INTO mobile_action_commit (
                action_key, tenant_id, task_id, device_id, account_id,
                binding_version, recipe_version_id, recipe_sha256,
                snapshot_sha256, action_id, parameter_hash, lease_id, status,
                before_evidence, resolution_revision, created_at, updated_at
            ) VALUES (
                ?, '00000000-0000-7000-8000-000000000b002',
                '00000000-0000-7000-8000-000000000b001',
                '00000000-0000-7000-8000-000000000b003',
                '00000000-0000-7000-8000-000000000b003',
                0, 'steps', '2' * 64, '2' * 64, 'confirm-delist', '3' * 64,
                'legacy-lease', 'INTENT', 'evidence://legacy', 0,
                '2026-09-16 09:00:00+00:00', '2026-09-16 09:00:00+00:00'
            )
            """,
            (legacy_key,),
        )
        connection.commit()

    command.upgrade(config, "head")
    with sqlite3.connect(database_path) as connection:
        columns = {
            str(row[1]) for row in connection.execute("PRAGMA table_info(mobile_action_commit)")
        }
        assert "platform_account_id" in columns
        assert connection.execute(
            "SELECT platform_account_id FROM mobile_action_commit WHERE action_key = ?",
            (legacy_key,),
        ).fetchone() == (None,)

    command.downgrade(config, "20260916_0023")
    with sqlite3.connect(database_path) as connection:
        columns = {
            str(row[1]) for row in connection.execute("PRAGMA table_info(mobile_action_commit)")
        }
        assert "platform_account_id" not in columns
        assert connection.execute(
            "SELECT status, resolution_revision FROM mobile_action_commit WHERE action_key = ?",
            (legacy_key,),
        ).fetchone() == ("INTENT", 0)

    command.upgrade(config, "head")
    with sqlite3.connect(database_path) as connection:
        assert "platform_account_id" in {
            str(row[1]) for row in connection.execute("PRAGMA table_info(mobile_action_commit)")
        }


# ---------------------------------------------------------------------------
# Real-PostgreSQL cross-connection commit visibility
# ---------------------------------------------------------------------------


async def test_postgres_intent_commit_visible_to_second_connection(api):  # noqa: F811
    """The intent commit must be visible to an independent connection pool
    (separate engine = separate connections) — SQLite cannot prove this."""

    client, app = api
    if app.state.database.engine.dialect.name != "postgresql":
        pytest.skip("cross-connection visibility requires disposable PostgreSQL")
    task, auth, body = await running(api)
    intent, _action = paths(task, body)
    assert (await client.post(intent, headers=auth, json=body)).status_code == 201

    second = Database(app.state.settings)
    try:
        async with second.unit_of_work() as session:
            row = await session.get(MobileActionCommitRow, body["actionKey"])
            assert row is not None
            assert row.status == "INTENT"
            task_row = await session.get(MobileTaskRow, task)
            assert row.platform_account_id == task_row.account_id
    finally:
        await second.dispose()
