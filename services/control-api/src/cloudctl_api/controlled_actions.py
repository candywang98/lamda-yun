"""Controlled-action identity pins, ledger phases and reconciliation proofs.

A13 (fleet-first backend line) factors the frozen controlled-action semantics
out of ``mobile_actions`` into pure, directly-testable helpers:

- contract pins + ``STABLE_IDENTITY_GOLDENS`` — six frozen identity vectors
  (probe / xianyu-steps / xhs / douyin / maintenance-v1 / v2). The
  xianyu-steps vector IS the cross-language golden
  ``mobile/companion/app/src/test/resources/steps-identity-golden.json``
  (verified by ``ControlledStepsIdentityTest`` on the Kotlin side), so any
  drift in ``action_identity`` breaks parity, not just local expectations.
- ``identity_inputs_free_of_envelope`` — fleet-identity/v1 §4 guard: the
  dynamic authorization envelope fields must never enter the
  actionKey/parameterHash input dict (mirror of the negative fixture
  ``k10-negative-actionkey-contains-epoch.json``).
- ``action_phase`` / ``phase_transition_allowed`` — the monotonic ledger
  state machine INTENT < REPORTED < RESOLVED. Ledger rows only ever move
  forward; late/duplicate events can never regress a phase.
- ``outcome_guard`` — the p09 outcome decision as a pure function. The check
  order and 409 messages are preserved verbatim from ``mobile_actions.outcome``
  (p09-ledger/20260910.1); the service now delegates to this guard.
- ``evidence_binding`` — the pure row-local binding record (target/account/
  lease window/task/versions/times) attached to action audit events. The
  account is taken from ``platform_account_id`` first, falling back to the
  legacy account_id (= deviceId for the steps families, fleet-identity/v1 §2
  recorded debt).
- ``platform_result_proven`` — a ledger row only counts as a *proven platform
  result* when the reconciliation actually closed it: revision > 0, terminal
  status, resolved_at set and non-empty resolution evidence.

The steps-family parameterHash keeps using deviceId as the account input:
that input is frozen cross-language (ControlledActionIdentity +
steps-identity-golden.json); changing it server-side would 409 every steps
intent. The real platform account is recorded in the new nullable
``mobile_action_commit.platform_account_id`` column (migration 0024) and is
deliberately NOT part of the ``_matches`` identity dict — legacy rows replay
with NULL and stay compatible.
"""

from __future__ import annotations

from typing import Any

from cloudctl_domain import ConflictError

from .db import MobileActionCommitRow
from .fleet_identity import AUTHORIZATION_ENVELOPE_FIELDS

# Contract pins (all FROZEN — cite, never restate):
CONTROLLED_ACTIONS_CONTRACT = "p09-ledger/20260910.1"
RECONCILIATION_CONTRACT = "p09-reconcile/20260910.1"
FLEET_ACTIONS_CONTRACT = "fleet-identity/v1@20260916.1"

# ---------------------------------------------------------------------------
# Frozen identity goldens (six families)
# ---------------------------------------------------------------------------

# Each vector pins the full identity input set plus the digests produced by
# mobile_actions.action_identity at freeze time. ``stepsSha256`` is the
# canonical_steps digest where the family is steps-based (snapshot == recipe
# == steps digest); the probe vector carries independent snapshot/recipe
# hashes from contracts/phase1/p09-action-identity-golden.json.
STABLE_IDENTITY_GOLDENS: dict[str, dict[str, Any]] = {
    "probe": {
        "taskId": "00000000-0000-7000-8000-000000000101",
        "commandType": "device.probe_capabilities.v1",
        "accountId": "00000000-0000-7000-8000-000000000202",
        "bindingVersion": 3,
        "snapshotSha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        "recipeSha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "actionId": "probe",
        "actionKey": "9f0109e8eff18337aff6a1d410d4c4f4ecff01bdc1808cad8710202c22470e17",
        "parameterHash": "c9257b2eb7ed1a1eece57e9f9a50c24920701f08aa0e7af56e8d263a7bf283d4",
    },
    "xianyu-steps": {
        # Verbatim cross-language golden (steps-identity-golden.json /
        # ControlledStepsIdentityTest): deviceId stands in as accountId.
        "taskId": "0a1b2c3d-1111-2222-3333-444455556666",
        "commandType": "xianyu.publish_listing.steps.v1",
        "accountId": "5d6e7f80-9999-8888-7777-666655554444",
        "bindingVersion": 0,
        "snapshotSha256": "ce231034efd1b3fae0c93a5ef37279544825ca233a833b86fdcdd57f298d81dd",
        "recipeSha256": "ce231034efd1b3fae0c93a5ef37279544825ca233a833b86fdcdd57f298d81dd",
        "actionId": "click-publish",
        "actionKey": "9f63c5cb30b2918dae74db0fdb091e62fd9ae4449eed530fafa216cdacdd39f0",
        "parameterHash": "af8ca357334d7ed7afb5ca173ffe9be49cf98cfb5aaf6e21e15174cf8df5b91f",
    },
    "xhs": {
        "taskId": "0a1b2c3d-1111-2222-3333-444455557703",
        "commandType": "xhs.publish_note.steps.v1",
        "accountId": "1d2e3f40-7777-6666-5555-444433332222",
        "bindingVersion": 0,
        "snapshotSha256": "77af08b5c368bfcc57a112b4cbd7dee1d4cdb8283c8902d5f39ef9418bff3848",
        "recipeSha256": "77af08b5c368bfcc57a112b4cbd7dee1d4cdb8283c8902d5f39ef9418bff3848",
        "actionId": "click-publish",
        "actionKey": "dfae61d8ed494a7188ab0ef0f6d7cf102b0b5bc8e4fd35ccf7656bfc32c89c6d",
        "parameterHash": "490397de17860bb45c0b05ced5031b6a91856b8628db3fada1ae03a4ef3280b9",
    },
    "douyin": {
        "taskId": "0a1b2c3d-1111-2222-3333-444455557704",
        "commandType": "douyin.publish_note.steps.v1",
        "accountId": "2d3e4f50-8888-7777-6666-555544443333",
        "bindingVersion": 2,
        "snapshotSha256": "29a47ca1389dca198fab583eb6f49db707476aad17ec6fd768c388595b9b6e17",
        "recipeSha256": "29a47ca1389dca198fab583eb6f49db707476aad17ec6fd768c388595b9b6e17",
        "actionId": "click-publish",
        "actionKey": "2105c2c856ab8b56edd61acc6483a7ee5b607b4f24cc933c8dff9391d70712cb",
        "parameterHash": "277f269cf00cfe00d592d754d39e0a4f20ac5f5ba36789885debba7df35e73d6",
    },
    "maintenance-v1": {
        "taskId": "0a1b2c3d-1111-2222-3333-444455557705",
        "commandType": "xianyu.delist.steps.v1",
        "accountId": "3d4e5f60-9999-8888-7777-666655554444",
        "bindingVersion": 0,
        "snapshotSha256": "3b8e7002e4d19ddf0615b6cd34ddca8e0a2a4e22ca90f8163cefd81091b3e2f5",
        "recipeSha256": "3b8e7002e4d19ddf0615b6cd34ddca8e0a2a4e22ca90f8163cefd81091b3e2f5",
        "actionId": "confirm-delist",
        "actionKey": "55ddeb7c0789531196dd8838973d85ff04ecf70881f12466f8eac9e1672d709a",
        "parameterHash": "671c174495f661794914ece1b6cc1fe6a03016f5315e67018c6e3168db40d1ab",
    },
    "maintenance-v2": {
        "taskId": "0a1b2c3d-1111-2222-3333-444455557706",
        "commandType": "xianyu.delist.steps.v2",
        "accountId": "3d4e5f60-9999-8888-7777-666655554444",
        "bindingVersion": 0,
        "snapshotSha256": "003b2571c218c788cff64303f45febdc8c9fa7dcb3b3a5dc20bdf9f856a6b854",
        "recipeSha256": "003b2571c218c788cff64303f45febdc8c9fa7dcb3b3a5dc20bdf9f856a6b854",
        "actionId": "confirm-delist",
        "actionKey": "89f3dad3299d47c3af6d007fecc15ebe85d6fccee54a621eb98771538c8ff99e",
        "parameterHash": "6c7ded1cec7b217774b1268990d0572553823ecbbe4fc08274d999c79fdfc9a3",
    },
}


def identity_inputs_free_of_envelope(identity_inputs: dict[str, Any]) -> list[str]:
    """fleet-identity/v1 §4 guard: envelope fields must not feed the hashes.

    Returns the dynamic authorization envelope field names found in the
    identity input dict (empty = clean). Mirrors the negative fixture
    ``k10-negative-actionkey-contains-epoch.json``: controlEpoch,
    fencingToken, leaseExpiresAt, sessionId and bootId belong to the
    dispatch-time AuthorizationEnvelope only — never to actionKey or
    parameterHash inputs.
    """

    return [name for name in AUTHORIZATION_ENVELOPE_FIELDS if name in identity_inputs]


# ---------------------------------------------------------------------------
# Monotonic ledger phase machine: INTENT < REPORTED < RESOLVED
# ---------------------------------------------------------------------------

ACTION_PHASE_INTENT = "INTENT"
ACTION_PHASE_REPORTED = "REPORTED"
ACTION_PHASE_RESOLVED = "RESOLVED"
ACTION_PHASE_ORDER = (ACTION_PHASE_INTENT, ACTION_PHASE_REPORTED, ACTION_PHASE_RESOLVED)

# Terminal ledger statuses (post-reconciliation only — CheckConstraint
# ck_mobile_action_status allows exactly INTENT/APPLIED/UNKNOWN/NOT_SUBMITTED).
TERMINAL_ACTION_STATUSES = frozenset({"APPLIED", "NOT_SUBMITTED"})


def _phase_from(status: str, resolution_revision: int) -> str:
    if resolution_revision:
        return ACTION_PHASE_RESOLVED
    if status == "INTENT":
        return ACTION_PHASE_INTENT
    return ACTION_PHASE_REPORTED


def action_phase(row: MobileActionCommitRow) -> str:
    """Current ledger phase of a commit row (INTENT < REPORTED < RESOLVED)."""

    return _phase_from(row.status, row.resolution_revision or 0)


def phase_transition_allowed(current: str, target: str) -> bool:
    """The ledger never regresses: target phase must rank >= current."""

    return ACTION_PHASE_ORDER.index(target) >= ACTION_PHASE_ORDER.index(current)


# ---------------------------------------------------------------------------
# Outcome guard (p09-ledger/20260910.1 — order and messages frozen verbatim)
# ---------------------------------------------------------------------------

OUTCOME_APPLY = "APPLY"
OUTCOME_REPLAY = "REPLAY"


def outcome_guard(
    *,
    row_status: str,
    row_parameter_hash: str,
    row_lease_id: str,
    row_reported_evidence: str | None,
    row_resolution_revision: int,
    row_before_evidence: str,
    task_business_state: str,
    body_parameter_hash: str,
    body_lease_id: str,
    body_status: str,
    body_evidence: str,
) -> str:
    """Pure p09 outcome decision: OUTCOME_APPLY, OUTCOME_REPLAY, or 409.

    Check order and ConflictError messages are preserved verbatim from the
    original mobile_actions.MobileActionService.outcome inline guards:

    1. outcome identity mismatch (parameterHash/lease)
    2. already resolved (phase RESOLVED) or task outside RECONCILING
    3. replay equality for already-reported rows (phase REPORTED)
    4. independent postcondition evidence for the first report
    """

    if body_parameter_hash != row_parameter_hash or body_lease_id != row_lease_id:
        raise ConflictError("outcome identity mismatch")
    if row_resolution_revision or task_business_state != "RECONCILING":
        # Phase machine: RESOLVED rows are immutable; the RECONCILING task
        # gate is the task-level mirror of the same monotonic rule.
        raise ConflictError("action already resolved or task not reconciling")
    if row_status != "INTENT":
        if row_status != body_status or row_reported_evidence != body_evidence:
            raise ConflictError("outcome replay differs")
        return OUTCOME_REPLAY
    if body_status == "APPLIED" and body_evidence == row_before_evidence:
        raise ConflictError("independent postcondition evidence required")
    return OUTCOME_APPLY


# ---------------------------------------------------------------------------
# Evidence binding and platform-result proof
# ---------------------------------------------------------------------------

# The legacy ledger account column carried the steps-family deviceId; the
# nullable platform_account_id column (migration 0024) records the real
# platform account when the task knows one. Binding reports prefer it.
ACCOUNT_SOURCE_PLATFORM = "platform_account_id"
ACCOUNT_SOURCE_LEGACY = "legacy_account_id"


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def evidence_binding(row: MobileActionCommitRow) -> dict[str, Any]:
    """Pure row-local reconciliation evidence binding.

    Everything the reconciliation trail needs to attribute an action:
    target device, account (platform_account_id first, legacy fallback),
    lease window, task, frozen versions, and row times. No joins, no I/O —
    ISO strings keep the dict JSON-safe for audit metadata.
    """

    platform_account = getattr(row, "platform_account_id", None)
    return {
        "contract": CONTROLLED_ACTIONS_CONTRACT,
        "taskId": row.task_id,
        "deviceId": row.device_id,
        "accountId": platform_account or row.account_id,
        "accountSource": (ACCOUNT_SOURCE_PLATFORM if platform_account else ACCOUNT_SOURCE_LEGACY),
        "leaseId": row.lease_id,
        "bindingVersion": row.binding_version,
        "recipeVersionId": row.recipe_version_id,
        "recipeSha256": row.recipe_sha256,
        "actionId": row.action_id,
        "createdAt": _iso(row.created_at),
        "updatedAt": _iso(row.updated_at),
        "resolvedAt": _iso(row.resolved_at),
    }


def platform_result_proven(row: MobileActionCommitRow) -> bool:
    """True only when reconciliation closed the row as a proven result.

    Requires the full closure conjunction: resolution revision > 0, a
    terminal status (APPLIED / NOT_SUBMITTED), an explicit resolved_at, and
    non-empty resolution evidence. Anything less (INTENT, reported-but-open
    UNKNOWN/APPLIED at revision 0, or a corrupt half-closed row) is NOT a
    platform result proof.
    """

    return (
        bool(row.resolution_revision)
        and row.resolution_revision > 0
        and row.status in TERMINAL_ACTION_STATUSES
        and row.resolved_at is not None
        and bool(row.resolution_evidence)
    )
