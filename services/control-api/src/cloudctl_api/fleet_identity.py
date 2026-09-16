"""Fleet identity policies and the Companion session registry.

Contract: contracts/fleet/v1/fleet-identity-v1.md (fleet-identity/v1@20260916.1,
FROZEN). This module implements the A10 *delta* on top of the existing
Enrollment/MobileBinding credential chain — it deliberately does not introduce
a second authentication scheme:

- ``FleetSessionRow`` registers one row per Companion *process registration*
  (sessionId minted at enroll/re-register time) plus the bootId, the closed
  capability table, and the raw gate states (§2). Every extension column is
  nullable so legacy rows/devices stay compatible ("先可空/兼容再收紧").
- ``normalize_capabilities`` / ``evaluate_executable`` implement the closed
  capability key set (§3) and the executable gates (§2: transport +
  accessibility enabled AND active + ime + screen-unlocked + engine>=min).
  ``online`` (transport heartbeat presence) and ``executable`` never merge.
- ``action_key`` / ``parameter_hash`` / ``build_authorization_envelope`` pin
  the stable-action-identity vs dynamic-authorization split (§4) by delegating
  to the single frozen formula in ``mobile_actions.action_identity``.
- ``account_write_conflict`` enforces the per-(tenantId, accountId) RUNNING
  write-task mutex across devices (§6.2 → 409 ACCOUNT_BUSY).
- ``open_unknown_actions`` blocks reclaim while open UNKNOWN ledger rows
  exist (§8 → 409 RECONCILE_REQUIRED, KEEP_WAITING semantics).
- ``required_capability_keys`` maps task families to the fleet capability keys
  they need (§3 → 422 INELIGIBLE_CAPABILITY at dispatch, never a task failure).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from cloudctl_domain import ConflictError, ValidationError
from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, select
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base, MobileActionCommitRow, MobileTaskRow, TimestampMixin

FLEET_IDENTITY_CONTRACT = "fleet-identity/v1@20260916.1"

# Closed capability key set, V1 (§3): new keys may only be appended.
CAPABILITY_KEYS = (
    "accessibility",
    "ime",
    "screen_capture",
    "media_projection",
    "flutter_anchors",
    "im_listen",
)

# Frozen executable gate names and order (§2 / positive fixture).
EXECUTABLE_GATE_ORDER = (
    "transport",
    "accessibility-enabled",
    "accessibility-active",
    "ime",
    "screen-unlocked",
    "engine>=min",
)

# Dynamic authorization envelope (§4): never part of actionKey/parameterHash.
AUTHORIZATION_ENVELOPE_FIELDS = (
    "controlEpoch",
    "fencingToken",
    "leaseExpiresAt",
    "sessionId",
    "bootId",
)

# Transport heartbeat presence window: a device is online while a heartbeat
# (enroll/authenticate/device-heartbeat all refresh last_seen_at) is recent.
ONLINE_GRACE_SECONDS = 90


class AccountBusyError(ConflictError):
    """fleet-identity/v1 §6.2: the account already has an active write task."""

    code = "ACCOUNT_BUSY"
    status = 409


class ReconcileRequiredError(ConflictError):
    """fleet-identity/v1 §8: open UNKNOWN ledger rows block reclaim."""

    code = "RECONCILE_REQUIRED"
    status = 409


class AuthorizationEnvelopeStaleError(ConflictError):
    """fleet-identity/v1 §4/§9: the lease was minted under a superseded session."""

    code = "AUTHORIZATION_ENVELOPE_STALE"
    status = 409


class IneligibleCapabilityError(ValidationError):
    """fleet-identity/v1 §3/§9: the device lacks a required capability."""

    code = "INELIGIBLE_CAPABILITY"
    status = 422


class FleetSessionRow(Base, TimestampMixin):
    """One Companion process session (sessionId minted per registration).

    Sessions are revoked, never deleted: a late heartbeat or replayed lease
    can observe ``revoked_at`` and must not resurrect the old session. The
    capability/gate columns are nullable so pre-A10 devices (which never
    negotiated) keep working; claim only applies the executable gates once a
    capability table has actually been negotiated.
    """

    __tablename__ = "fleet_device_session"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    device_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("device.id"), index=True, nullable=False
    )
    binding_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("mobile_binding.id"), index=True, nullable=False
    )
    boot_id: Mapped[str | None] = mapped_column(String(128))
    companion_version: Mapped[str | None] = mapped_column(String(128))
    engine_version: Mapped[int | None] = mapped_column(Integer)
    capabilities: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    accessibility_enabled: Mapped[bool | None] = mapped_column(Boolean)
    accessibility_active: Mapped[bool | None] = mapped_column(Boolean)
    ime_ready: Mapped[bool | None] = mapped_column(Boolean)
    screen_unlocked: Mapped[bool | None] = mapped_column(Boolean)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def device_online(last_seen_at: datetime | None, now: datetime) -> bool:
    """§2: ``online`` is transport heartbeat presence — nothing more."""
    return last_seen_at is not None and _aware(last_seen_at) > now - timedelta(
        seconds=ONLINE_GRACE_SECONDS
    )


# ---------------------------------------------------------------------------
# Stable action identity vs dynamic authorization envelope (§4)
# ---------------------------------------------------------------------------


def action_key(task_id: str, recipe_sha256: str, action_id: str) -> str:
    """actionKey = sha256("cloudctl.action/v1\\n{taskId}\\n{recipeSha256}\\n{actionId}").

    Delegates to the single frozen implementation (mobile_actions.action_identity)
    so the ledger and this contract view can never diverge; the placeholder
    inputs only feed the parameter hash, which is discarded here.
    """
    from .mobile_actions import action_identity

    key, _ = action_identity(
        task_id, "fleet.v1", "fleet", 1, recipe_sha256, recipe_sha256, action_id
    )
    return key


def parameter_hash(
    task_id: str,
    command_type: str,
    account_id: str,
    binding_version: int,
    snapshot_sha256: str,
    recipe_sha256: str,
) -> str:
    """parameterHash per §4 (bindingVersion participates; sessionId never does)."""
    from .mobile_actions import action_identity

    return action_identity(
        task_id, command_type, account_id, binding_version, snapshot_sha256, recipe_sha256, "fleet"
    )[1]


def build_authorization_envelope(
    *,
    control_epoch: int,
    fencing_token: int,
    lease_expires_at: str,
    session_id: str,
    boot_id: str | None,
) -> dict[str, Any]:
    """The dynamic authorization envelope (§4): dispatch-time only, never hashed."""
    return {
        "controlEpoch": control_epoch,
        "fencingToken": fencing_token,
        "leaseExpiresAt": lease_expires_at,
        "sessionId": session_id,
        "bootId": boot_id,
    }


# ---------------------------------------------------------------------------
# Capability table (§3)
# ---------------------------------------------------------------------------


def normalize_capabilities(
    value: dict[str, Any] | None,
) -> dict[str, dict[str, Any]] | None:
    """Validate a reported capability table against the closed V1 key set.

    ``None`` means "not negotiated" (legacy compatibility). Keys the device did
    not report are normalized to ``{"supported": False}`` (fail-closed for the
    task families that require them); unknown keys are rejected outright.
    """
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValidationError("capabilities must be an object keyed by capability name")
    unknown = sorted(set(value) - set(CAPABILITY_KEYS))
    if unknown:
        raise ValidationError(f"unknown capability keys (closed set v1): {unknown}")
    normalized: dict[str, dict[str, Any]] = {}
    for key in CAPABILITY_KEYS:
        entry = value.get(key)
        if entry is None:
            normalized[key] = {"supported": False}
            continue
        if not isinstance(entry, dict):
            raise ValidationError(f"capability {key} must be an object")
        supported = entry.get("supported")
        if not isinstance(supported, bool):
            raise ValidationError(f"capability {key} requires a boolean 'supported'")
        item: dict[str, Any] = {"supported": supported}
        engine_min = entry.get("engineMin")
        if engine_min is not None:
            if isinstance(engine_min, bool) or not isinstance(engine_min, int) or engine_min < 1:
                raise ValidationError(f"capability {key} engineMin must be a positive integer")
            item["engineMin"] = engine_min
        normalized[key] = item
    return normalized


def negotiated_engine_min(capabilities: dict[str, Any] | None) -> int | None:
    """Highest engine minimum among the capabilities the device supports."""
    if not capabilities:
        return None
    minima = [
        int(entry.get("engineMin", 1))
        for entry in capabilities.values()
        if isinstance(entry, dict) and entry.get("supported")
    ]
    return max(minima) if minima else None


def evaluate_executable(
    *,
    online: bool,
    accessibility_enabled: bool | None,
    accessibility_active: bool | None,
    ime_ready: bool | None,
    screen_unlocked: bool | None,
    engine_version: int | None,
    engine_min: int | None,
) -> tuple[bool, list[str], list[str]]:
    """§2 executable gates.

    Returns ``(executable, passed_gates, failed_gates)`` in the frozen gate
    order. A gate whose input was never reported (``None``) is not evaluated —
    that is the compatibility path for devices that have not negotiated a
    capability profile yet ("先可空/兼容再收紧"); once a value is reported it
    is authoritative and ``False`` fails the gate.
    """
    evaluated: list[tuple[str, bool]] = [("transport", bool(online))]
    if accessibility_enabled is not None:
        evaluated.append(("accessibility-enabled", bool(accessibility_enabled)))
    if accessibility_active is not None:
        evaluated.append(("accessibility-active", bool(accessibility_active)))
    if ime_ready is not None:
        evaluated.append(("ime", bool(ime_ready)))
    if screen_unlocked is not None:
        evaluated.append(("screen-unlocked", bool(screen_unlocked)))
    if engine_version is not None and engine_min is not None:
        evaluated.append(("engine>=min", engine_version >= engine_min))
    executable = all(passed for _, passed in evaluated)
    order = {name: index for index, name in enumerate(EXECUTABLE_GATE_ORDER)}
    passed_gates = sorted(
        (name for name, passed in evaluated if passed), key=order.__getitem__
    )
    failed_gates = sorted(
        (name for name, passed in evaluated if not passed), key=order.__getitem__
    )
    return executable, passed_gates, failed_gates


# Task families → required fleet capability keys (§3: 缺必备能力 → INELIGIBLE).
FLEET_REQUIRED_CAPABILITIES: dict[str, tuple[str, ...]] = {
    "xianyu.publish_listing.v1": ("accessibility", "ime", "screen_capture"),
    "xianyu.publish_listing.steps.v1": ("accessibility", "ime", "screen_capture"),
    "xiaohongshu.publish_note.v1": ("accessibility", "ime", "screen_capture"),
    "xhs.publish_note.steps.v1": ("accessibility", "ime", "screen_capture", "flutter_anchors"),
    "douyin.publish_note.steps.v1": ("accessibility", "ime", "screen_capture"),
    "xianyu.collect_orders.v1": ("accessibility", "screen_capture"),
    "xianyu.collect_orders.steps.v1": ("accessibility", "screen_capture"),
    "xianyu.collect_orders.steps.v2": ("accessibility", "screen_capture"),
    "device.probe_capabilities.v1": ("accessibility",),
    "xianyu.polish.steps.v1": ("accessibility", "screen_capture"),
    "xianyu.delist.steps.v1": ("accessibility", "screen_capture"),
    "xianyu.delete_delisted.steps.v1": ("accessibility", "screen_capture"),
    "xianyu.delist.steps.v2": ("accessibility", "screen_capture"),
    "xianyu.delete_delisted.steps.v2": ("accessibility", "screen_capture"),
}
# Legacy steps tasks (commandType null) are classified by their frozen package
# family — the same packages STEPS_SHAPES covers in mobile_actions.
LEGACY_STEPS_PACKAGE_CAPABILITIES = {
    "com.taobao.idlefish": ("accessibility", "ime", "screen_capture"),
    "com.xingin.xhs": ("accessibility", "ime", "screen_capture", "flutter_anchors"),
    "com.ss.android.ugc.aweme": ("accessibility", "ime", "screen_capture"),
}


def required_capability_keys(task: MobileTaskRow) -> tuple[str, ...]:
    if task.command_type:
        return FLEET_REQUIRED_CAPABILITIES.get(task.command_type, ())
    return LEGACY_STEPS_PACKAGE_CAPABILITIES.get(task.target_package or "", ())


def capability_shortfall(
    task: MobileTaskRow, capabilities: dict[str, Any]
) -> list[str]:
    """Required capability keys the negotiated table does not support."""
    return [
        key
        for key in required_capability_keys(task)
        if not (capabilities.get(key) or {}).get("supported")
    ]


# ---------------------------------------------------------------------------
# Account write mutex (§6.2)
# ---------------------------------------------------------------------------

# Read-only task families, explicitly declared (writeEffect=false). Everything
# else — including unknown/legacy command types — is treated as a write so the
# mutex fails closed.
READ_COMMAND_TYPES = frozenset(
    {
        "xianyu.collect_orders.v1",
        "xianyu.collect_orders.steps.v1",
        "xianyu.collect_orders.steps.v2",
        "device.probe_capabilities.v1",
    }
)


def task_write_effect(task: MobileTaskRow) -> bool:
    if task.command_type:
        return task.command_type not in READ_COMMAND_TYPES
    return True


async def account_write_conflict(
    session: Any, tenant_id: str, account_id: str, *, exclude_task_id: str
) -> MobileTaskRow | None:
    """First cross-device active write task for the account, if any (§6.2)."""
    rows = cast(
        "list[MobileTaskRow]",
        (
            await session.execute(
                select(MobileTaskRow).where(
                    MobileTaskRow.tenant_id == tenant_id,
                    MobileTaskRow.account_id == account_id,
                    MobileTaskRow.status.in_(("CLAIMED", "RUNNING")),
                )
            )
        ).scalars(),
    )
    for row in rows:
        if row.id != exclude_task_id and task_write_effect(row):
            return row
    return None



# ---------------------------------------------------------------------------
# Open-UNKNOWN reclaim guard (§8)
# ---------------------------------------------------------------------------


async def open_unknown_actions(
    session: Any, tenant_id: str, device_id: str
) -> list[MobileActionCommitRow]:
    """Unresolved UNKNOWN ledger rows on this device's tasks (any task state)."""
    task_ids = select(MobileTaskRow.id).where(
        MobileTaskRow.tenant_id == tenant_id,
        MobileTaskRow.device_id == device_id,
    )
    return list(
        (
            await session.execute(
                select(MobileActionCommitRow).where(
                    MobileActionCommitRow.tenant_id == tenant_id,
                    MobileActionCommitRow.status == "UNKNOWN",
                    MobileActionCommitRow.resolved_at.is_(None),
                    MobileActionCommitRow.task_id.in_(task_ids),
                )
            )
        ).scalars()
    )


# ---------------------------------------------------------------------------
# Session registry
# ---------------------------------------------------------------------------


def new_session_id() -> str:
    return f"sess-{uuid.uuid4().hex}"


async def register_session_row(
    session: Any,
    *,
    tenant_id: str,
    device_id: str,
    binding_id: str,
    now: datetime,
    boot_id: str | None = None,
    companion_version: str | None = None,
    capabilities: dict[str, Any] | None = None,
    accessibility_enabled: bool | None = None,
    accessibility_active: bool | None = None,
    ime_ready: bool | None = None,
    screen_unlocked: bool | None = None,
    engine_version: int | None = None,
) -> FleetSessionRow:
    """Register a fresh Companion process session and revoke the prior ones.

    Revocation (not deletion) is what makes late heartbeats from an old
    session observable: the envelope check compares the lease's stamped
    sessionId/bootId against the current active session and rejects mismatches.
    """
    others = (
        await session.execute(
            select(FleetSessionRow)
            .where(
                FleetSessionRow.device_id == device_id,
                FleetSessionRow.revoked_at.is_(None),
            )
            .with_for_update()
        )
    ).scalars()
    for other in others:
        other.revoked_at = now
    row = FleetSessionRow(
        id=str(uuid.uuid4()),
        session_id=new_session_id(),
        tenant_id=tenant_id,
        device_id=device_id,
        binding_id=binding_id,
        boot_id=boot_id,
        companion_version=companion_version,
        engine_version=engine_version,
        capabilities=normalize_capabilities(capabilities),
        accessibility_enabled=accessibility_enabled,
        accessibility_active=accessibility_active,
        ime_ready=ime_ready,
        screen_unlocked=screen_unlocked,
        last_seen_at=now,
        revoked_at=None,
        created_at=now,
    )
    session.add(row)
    await session.flush()
    return row


async def active_session(
    session: Any, tenant_id: str, binding_id: str
) -> FleetSessionRow | None:
    return cast(
        "FleetSessionRow | None",
        await session.scalar(
            select(FleetSessionRow)
            .where(
                FleetSessionRow.tenant_id == tenant_id,
                FleetSessionRow.binding_id == binding_id,
                FleetSessionRow.revoked_at.is_(None),
            )
            .order_by(FleetSessionRow.created_at.desc())
        ),
    )


def session_envelope(
    row: FleetSessionRow | None,
    *,
    tenant_id: str,
    device_id: str,
    online: bool,
) -> dict[str, Any]:
    """FleetEnvelope view (§2): online and executable are reported separately."""
    if row is None:
        return {
            "contract": FLEET_IDENTITY_CONTRACT,
            "tenantId": tenant_id,
            "deviceId": device_id,
            "sessionId": None,
            "bootId": None,
            "online": online,
            "executable": online,
            "executableGates": ["transport"] if online else [],
            "failedGates": [] if online else ["transport"],
            "capabilities": None,
            "companionVersion": None,
            "engineVersion": None,
            "lastSeenAt": None,
        }
    executable, passed, failed = evaluate_executable(
        online=online,
        accessibility_enabled=row.accessibility_enabled,
        accessibility_active=row.accessibility_active,
        ime_ready=row.ime_ready,
        screen_unlocked=row.screen_unlocked,
        engine_version=row.engine_version,
        engine_min=negotiated_engine_min(row.capabilities),
    )
    return {
        "contract": FLEET_IDENTITY_CONTRACT,
        "tenantId": tenant_id,
        "deviceId": device_id,
        "sessionId": row.session_id,
        "bootId": row.boot_id,
        "online": online,
        "executable": executable,
        "executableGates": passed,
        "failedGates": failed,
        "capabilities": row.capabilities,
        "companionVersion": row.companion_version,
        "engineVersion": row.engine_version,
        "lastSeenAt": row.last_seen_at,
    }


def lease_envelope_stale(
    *, recorded_session_id: Any, recorded_boot_id: Any, current: FleetSessionRow | None
) -> bool:
    """§2/§4: a lease minted under a superseded session/boot must not run."""
    if recorded_session_id is None and recorded_boot_id is None:
        return False
    if current is None:
        return True
    if recorded_session_id is not None and current.session_id != recorded_session_id:
        return True
    if (
        recorded_boot_id is not None
        and current.boot_id is not None
        and current.boot_id != recorded_boot_id
    ):
        return True
    return False
