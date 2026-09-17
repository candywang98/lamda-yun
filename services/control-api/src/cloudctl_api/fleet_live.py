"""Fleet live tiered sessions (L10) implementing live-capabilities/v1 (K13).

Layering on top of the slice1 module (``cloudctl_api.live``, p10-live):

- Read/view permission and the remote write lease are separate: a session in
  VIEWING holds only a ``device_lease`` marker row (owner_type "LIVE") that
  never blocks task claims; REMOTE upgrades the row to the write lease
  (owner_type "REMOTE") which the existing claim path already refuses —
  the DB row, not any in-process ``has_remote`` flag, is the single arbiter
  for cross-process contention.
- Sessions bind the four-tuple (tenantId, deviceId, operatorId, sessionId)
  plus an opaque session token; every operation re-validates the binding.
- The transport is chosen explicitly at establishment from the closed
  tier × transport matrix: JPEG tiers ride the default JPEG-over-HTTPS
  adapter with zero TURN dependency; the WEBRTC tier refuses to establish
  without TURN configuration (503 LIVE_TURN_UNAVAILABLE, no silent
  downgrade). Adapter implementations live in ``fleet_live_transport``
  (services/edge-hub/src).
- Disconnect reclaims resources and does not auto-restore authorization:
  REMOTE is force-released on disconnect and the session closes after the
  grace window; reuse of the old token is 410 LIVE_SESSION_TERMINAL.

Session semantics follow the frozen contract; conflicts between slice1 and
the contract are out of scope for this module (report, never patch K13).
"""

from __future__ import annotations

import asyncio
import os
import secrets
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal

from cloudctl_domain import (
    Actor,
    AuthenticationError,
    ConflictError,
    DomainError,
    NotFoundError,
)
from fastapi import APIRouter, Depends, Header, Request
from fleet_live_transport import (
    TransportUnavailable,
    TransportUnsupported,
    TurnConfig,
    default_registry,
)
from pydantic import BaseModel, Field
from sqlalchemy import select, update

from .auth import current_actor
from .db import AuditEventRow, DeviceLeaseRow, DeviceRow, MobileTaskRow
from .fleet_identity import open_unknown_actions
from .live import (
    CLOSED,
    FRAME_GRACE_S,
    FRAME_STALE_S,
    REMOTE,
    SESSION_HARD_LIMIT_S,
    VIEWING,
)
from .mobile_routes import Binding
from .mobile_service import MobileTaskService

# device_lease.owner_type values used by the live lane. "REMOTE" is the value
# the task-claim path already refuses ("device write lease is held by remote
# control"); "LIVE" marks a read-only session row that never blocks claims.
LEASE_OWNER_LIVE = "LIVE"
LEASE_OWNER_REMOTE = "REMOTE"
LIVE_WORKFLOW_PREFIX = "live/"
SESSION_TOKEN_HEADER = "X-Live-Session-Token"  # noqa: S105 - header name, not a secret
MAX_INPUT_RATE_PER_S = 10
DEFAULT_TTL_EXPIRY_MS = 2000
DEFAULT_STALE_FRAME_THRESHOLD = 10
SEQ_REGRESSION_WINDOW_S = 5.0
SEQ_REGRESSION_DROP_AFTER = 3


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


# ---------------------------------------------------------------------------
# K13 §9 problem codes (DomainError subclasses keep the shared envelope)
# ---------------------------------------------------------------------------


class LiveTierUnsupportedError(DomainError):
    code = "LIVE_TIER_UNSUPPORTED"
    status = 422


class LiveSessionTerminalError(DomainError):
    code = "LIVE_SESSION_TERMINAL"
    status = 410


class LiveInputForbiddenError(DomainError):
    code = "LIVE_INPUT_FORBIDDEN"
    status = 403


class InputExpiredError(DomainError):
    code = "INPUT_EXPIRED"
    status = 422


class InputSeqRegressionError(DomainError):
    code = "INPUT_SEQ_REGRESSION"
    status = 422


class LiveRateLimitedError(DomainError):
    code = "LIVE_RATE_LIMITED"
    status = 429


class LiveAuthRequiredError(DomainError):
    code = "LIVE_AUTH_REQUIRED"
    status = 428


class LiveTurnUnavailableError(DomainError):
    code = "LIVE_TURN_UNAVAILABLE"
    status = 503


# ---------------------------------------------------------------------------
# K13 §1 tier table (derived constants, closed set)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class LiveTierSpec:
    tier: str
    transport: str
    allows_input: bool
    ui_label: str
    turn_required: bool
    gates: tuple[str, ...]
    input_policy: dict[str, Any] | None = None


_INPUT_POLICY = {
    "maxInputRatePerSecond": MAX_INPUT_RATE_PER_S,
    "ttlExpiryMs": DEFAULT_TTL_EXPIRY_MS,
    "staleFrameThreshold": DEFAULT_STALE_FRAME_THRESHOLD,
    "seqRequired": True,
    "frameSeqRequired": True,
}

LIVE_TIERS: dict[str, LiveTierSpec] = {
    "JPEG_PREVIEW": LiveTierSpec(
        tier="JPEG_PREVIEW",
        transport="JPEG_WS",
        allows_input=False,
        ui_label="preview",
        turn_required=False,
        gates=(
            "GATE_LIVE_LEASE",
            "GATE_MEDIAPROJECTION_AUTH",
            "GATE_JPEG_TRANSPORT",
        ),
    ),
    "INTERACTIVE_REMOTE": LiveTierSpec(
        tier="INTERACTIVE_REMOTE",
        transport="JPEG_WS",
        allows_input=True,
        ui_label="interactive",
        turn_required=False,
        gates=(
            "GATE_LIVE_LEASE",
            "GATE_MEDIAPROJECTION_AUTH",
            "GATE_JPEG_TRANSPORT",
            "GATE_OPERATOR_WRITE",
            "GATE_INPUT_RATELIMIT",
        ),
        input_policy=dict(_INPUT_POLICY),
    ),
    "WEBRTC": LiveTierSpec(
        tier="WEBRTC",
        transport="WEBRTC",
        allows_input=True,
        ui_label="interactive-hd",
        turn_required=True,
        gates=(
            "GATE_LIVE_LEASE",
            "GATE_MEDIAPROJECTION_AUTH",
            "GATE_OPERATOR_WRITE",
            "GATE_INPUT_RATELIMIT",
            "GATE_TURN_DEPLOY",
            "GATE_BANDWIDTH_BUDGET",
            "GATE_SECURITY_REVIEW",
        ),
        input_policy=dict(_INPUT_POLICY),
    ),
}

# Default frame descriptor (K13 §3): delivered with session capabilities; the
# companion re-delivers on geometry changes from the next frameSeq.
DEFAULT_FRAME_GEOMETRY = {
    "frameWidth": 405,
    "frameHeight": 720,
    "deviceWidth": 1080,
    "deviceHeight": 1920,
    "rotation": 0,
}

TERMINAL_CAUSES = {
    "OPERATOR_STOP",
    "TIMEOUT_30M",
    "DISCONNECT_GRACE_EXPIRED",
    "DEVICE_REBOOT",
    "PROJECTION_REVOKED",
    "SERVICE_CRASH",
    "SERVER_CLOSED",
}


# ---------------------------------------------------------------------------
# Session projection (in-memory cache; the lease row stays the arbiter)
# ---------------------------------------------------------------------------


class FleetLiveSession:
    def __init__(
        self,
        *,
        sid: str,
        tenant_id: str,
        device_id: str,
        operator_id: str,
        tier_spec: LiveTierSpec,
        epoch: int,
        lease_id: str,
        established_at: datetime,
        token: str,
        transport_plan: Any,
    ) -> None:
        self.sid = sid
        self.tenant_id = tenant_id
        self.device_id = device_id
        self.operator_id = operator_id
        self.tier_spec = tier_spec
        self.epoch = epoch
        self.lease_id = lease_id
        self.established_at = established_at
        self.expires_at = established_at + timedelta(seconds=SESSION_HARD_LIMIT_S)
        self.token = token
        self.transport_plan = transport_plan
        self.state = VIEWING
        self.authorization_confirmed_at: datetime | None = None
        self.closed_cause: str | None = None
        self.closed_at: datetime | None = None
        # K13 §4 watermarks.
        self.input_watermark = 0
        self.latest_frame_seq = 0
        self.frame_delivered_at: dict[int, float] = {}
        self.input_times: list[float] = []
        self.seq_regressions: list[float] = []
        # Liveness / disconnect bookkeeping (monotonic).
        self.established_monotonic = time.monotonic()
        self.last_frame_monotonic = self.established_monotonic
        self.operator_lost_monotonic: float | None = None
        self.companion_lost_monotonic: float | None = None
        self.operator_socket: Any = None
        self.companion_socket: Any = None

    # ---- pure checks (unit-testable) ----
    @property
    def closed(self) -> bool:
        return self.state == CLOSED

    def check_input(self, message: dict[str, Any], now_monotonic: float) -> str | None:
        """K13 §4 rejection rules; returns None when the input is accepted."""
        spec = self.tier_spec
        # Rule 4 first: read-only tier or non-REMOTE state rejects ANY input.
        if self.state != REMOTE or not spec.allows_input:
            return "LIVE_INPUT_FORBIDDEN"
        seq = int(message.get("seq", 0))
        frame_seq = int(message.get("frameSeq", 0))
        # Rule 1: seq duplicate/regression.
        if seq <= self.input_watermark:
            self.seq_regressions = [
                stamp
                for stamp in self.seq_regressions
                if now_monotonic - stamp < SEQ_REGRESSION_WINDOW_S
            ]
            self.seq_regressions.append(now_monotonic)
            return "INPUT_SEQ_REGRESSION"
        policy = spec.input_policy or {}
        # Rule 2: frame watermark staleness.
        threshold = int(policy.get("staleFrameThreshold", DEFAULT_STALE_FRAME_THRESHOLD))
        if self.latest_frame_seq - frame_seq > threshold:
            return "INPUT_EXPIRED"
        # Rule 3: gesture TTL against the delivered frame timestamp.
        ttl_s = int(policy.get("ttlExpiryMs", DEFAULT_TTL_EXPIRY_MS)) / 1000.0
        delivered = self.frame_delivered_at.get(frame_seq)
        if delivered is None or now_monotonic - delivered > ttl_s:
            return "INPUT_EXPIRED"
        # Rule 5: input rate.
        rate = int(policy.get("maxInputRatePerSecond", MAX_INPUT_RATE_PER_S))
        self.input_times = [
            stamp for stamp in self.input_times if now_monotonic - stamp < 1.0
        ]
        if len(self.input_times) >= rate:
            return "LIVE_RATE_LIMITED"
        self.input_times.append(now_monotonic)
        self.input_watermark = seq
        return None

    def should_drop_remote(self, code: str, now_monotonic: float) -> bool:
        """Whether a rejection code severs the REMOTE grant (K13 §4/§5)."""
        if code == "LIVE_RATE_LIMITED":
            return True
        if code == "INPUT_SEQ_REGRESSION":
            recent = [
                stamp
                for stamp in self.seq_regressions
                if now_monotonic - stamp < SEQ_REGRESSION_WINDOW_S
            ]
            return len(recent) >= SEQ_REGRESSION_DROP_AFTER
        return False


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class FleetLiveService:
    """Tiered live sessions with DB-leased write arbitration."""

    def __init__(
        self,
        mobile: MobileTaskService,
        *,
        turn_config: TurnConfig | None = None,
        registry: Any = None,
    ) -> None:
        self.mobile = mobile
        self.database = mobile.database
        self.sessions: dict[str, FleetLiveSession] = {}
        self.lock = asyncio.Lock()
        self._turn_config = turn_config
        self._registry = registry or default_registry(
            turn_config if turn_config is not None else TurnConfig.from_env(os.environ)
        )

    # ---- helpers ----
    def _audit(
        self,
        db: Any,
        live: FleetLiveSession,
        action: str,
        actor_id: str,
        *,
        result: str = "SUCCESS",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        db.add(
            AuditEventRow(
                id=str(uuid.uuid4()),
                tenant_id=live.tenant_id,
                actor_id=actor_id,
                actor_type="operator",
                resource_type="live_session",
                resource_id=live.sid,
                request_id=str(uuid.uuid4()),
                device_id=live.device_id,
                action=f"live.session.{action}",
                metadata_json={
                    "state": live.state,
                    "tier": live.tier_spec.tier,
                    **(metadata or {}),
                },
                occurred_at=_utcnow(),
                result=result,
            )
        )

    def _session_or_not_found(
        self, actor: Actor, sid: str, device_id: str | None = None
    ) -> FleetLiveSession:
        live = self.sessions.get(sid)
        if live is None or live.tenant_id != str(actor.tenant_id):
            # K13 §9: tenant over-reach reuses NOT_FOUND.
            raise NotFoundError("live session was not found")
        if live.operator_id != str(actor.user_id):
            # Four-tuple binding: another operator's session is invisible.
            raise NotFoundError("live session was not found")
        if device_id is not None and live.device_id != device_id:
            raise NotFoundError("live session was not found")
        return live

    def _authenticate(
        self, actor: Actor, device_id: str | None, sid: str, token: str | None
    ) -> FleetLiveSession:
        live = self._session_or_not_found(actor, sid, device_id)
        if not token or not secrets.compare_digest(live.token, token):
            raise AuthenticationError("live session token is invalid")
        return live

    def _require_open(self, live: FleetLiveSession) -> None:
        if live.closed:
            raise LiveSessionTerminalError(
                f"live session is terminal ({live.closed_cause}); "
                "re-initiate with a fresh MediaProjection authorization"
            )

    @staticmethod
    def _is_live_row(row: DeviceLeaseRow | None) -> bool:
        return row is not None and row.owner_workflow_id.startswith(LIVE_WORKFLOW_PREFIX)

    @staticmethod
    def _row_active(row: DeviceLeaseRow | None, now: datetime) -> bool:
        return row is not None and row.canceled_at is None and _aware(row.expires_at) > now

    def _workflow_id(self, live: FleetLiveSession) -> str:
        return f"{LIVE_WORKFLOW_PREFIX}{live.sid}"

    async def _transact(self, work: Any, *args: Any) -> Any:
        """Run work(db) in one UoW; DomainErrors re-raise AFTER commit.

        Rejection and close side effects (audits, lease downgrades, row
        cancels) must survive the error response: K13 §4 requires rejected
        inputs to stay audited, and a sweep-triggered close must cancel the
        lease row even when the triggering request then fails 410. The
        default unit-of-work rollback on exception would discard them.
        """
        captured: DomainError | None = None
        async with self.lock, self.database.unit_of_work() as db:
            try:
                return await work(db, *args)
            except DomainError as exc:
                captured = exc
        assert captured is not None
        raise captured

    # ---- lifecycle ----
    async def establish(
        self,
        actor: Actor,
        device_id: str,
        tier: str,
        transport: str | None = None,
    ) -> dict[str, Any]:
        spec = LIVE_TIERS.get(tier)
        if spec is None:
            raise LiveTierUnsupportedError(f"unknown live tier: {tier!r}")
        sid = str(uuid.uuid4())
        try:
            adapter = self._registry.select(tier, transport)
            plan = adapter.prepare(
                session_id=sid,
                device_id=device_id,
                tenant_id=str(actor.tenant_id),
                tier=tier,
            )
        except TransportUnsupported as exc:
            raise LiveTierUnsupportedError(str(exc)) from exc
        except TransportUnavailable as exc:
            # WEBRTC without TURN: refuse, never silently downgrade (K13 §8).
            raise LiveTurnUnavailableError(str(exc)) from exc
        async with self.lock, self.database.unit_of_work() as db:
            device = await db.get(DeviceRow, device_id, with_for_update=True)
            if device is None or device.tenant_id != str(actor.tenant_id):
                raise NotFoundError("device was not found")
            row = await db.get(DeviceLeaseRow, device_id, with_for_update=True)
            now = _utcnow()
            if self._row_active(row, now) and self._is_live_row(row):
                raise ConflictError(
                    "LIVE_SESSION_EXISTS: device already has an active live session"
                )
            if row is not None:
                # Mirror the claim path's lane replacement (lease rows are
                # ephemeral markers; task fencing lives on MobileTaskRow).
                await db.delete(row)
                await db.flush()
            device.fencing_counter += 1
            live = FleetLiveSession(
                sid=sid,
                tenant_id=str(actor.tenant_id),
                device_id=device_id,
                operator_id=str(actor.user_id),
                tier_spec=spec,
                epoch=device.fencing_counter,
                lease_id=str(uuid.uuid4()),
                established_at=now,
                token=secrets.token_urlsafe(24),
                transport_plan=plan,
            )
            db.add(
                DeviceLeaseRow(
                    device_id=device_id,
                    tenant_id=live.tenant_id,
                    lease_id=live.lease_id,
                    owner_workflow_id=self._workflow_id(live),
                    fencing_token=device.fencing_counter,
                    expires_at=live.expires_at,
                    canceled_at=None,
                    owner_type=LEASE_OWNER_LIVE,
                    created_at=now,
                )
            )
            self.sessions[sid] = live
            self._audit(db, live, "established", str(actor.user_id))
            self._audit(
                db,
                live,
                "tier.granted",
                str(actor.user_id),
                metadata={"transport": spec.transport, "gates": list(spec.gates)},
            )
            return self.view(live, include_token=True)

    async def ack_projection(
        self,
        *,
        tenant_id: str,
        device_id: str,
        sid: str,
        granted: bool,
        confirmed_at: datetime | None = None,
    ) -> dict[str, Any]:
        async with self.lock, self.database.unit_of_work() as db:
            live = self.sessions.get(sid)
            if (
                live is None
                or live.tenant_id != tenant_id
                or live.device_id != device_id
            ):
                raise NotFoundError("live session was not found")
            if granted:
                live.authorization_confirmed_at = confirmed_at or _utcnow()
                self._audit(db, live, "authorization.ack", "companion")
            else:
                # User denied MediaProjection: terminal, no retry on this sid.
                await self._close_locked(db, live, "PROJECTION_REVOKED")
            return self.view(live)

    async def take_control(self, actor: Actor, sid: str, token: str | None) -> dict[str, Any]:
        async def work(db: Any) -> dict[str, Any]:
            live = self._authenticate(actor, None, sid, token)
            await self._sweep_locked(db, live)
            self._require_open(live)
            if live.state == REMOTE:
                return self.view(live)
            if not live.tier_spec.allows_input:
                # Capability boundary first: a read-only tier can never take
                # control, regardless of the authorization state.
                raise LiveInputForbiddenError(
                    f"tier {live.tier_spec.tier} is read-only and cannot take control"
                )
            if live.authorization_confirmed_at is None:
                raise LiveAuthRequiredError(
                    "MediaProjection authorization must be confirmed before take-control"
                )
            device = await db.get(DeviceRow, live.device_id, with_for_update=True)
            assert device is not None
            row = await db.get(DeviceLeaseRow, live.device_id, with_for_update=True)
            now = _utcnow()
            if (
                self._row_active(row, now)
                and row is not None
                and row.owner_type == LEASE_OWNER_REMOTE
                and row.owner_workflow_id != self._workflow_id(live)
            ):
                # Cross-process safe: the DB row decides, first writer wins.
                raise ConflictError(
                    "LIVE_REMOTE_HELD: another session holds the remote write lease"
                )
            # Single writer: force running tasks into the operator lane
            # (same semantics as slice1 take-control).
            await db.execute(
                update(MobileTaskRow)
                .where(
                    MobileTaskRow.device_id == live.device_id,
                    MobileTaskRow.business_state == "RUNNING",
                )
                .values(business_state="PAUSED_WAITING_USER", stall_reason="live remote control")
            )
            device.fencing_counter += 1
            if row is None:
                db.add(
                    DeviceLeaseRow(
                        device_id=live.device_id,
                        tenant_id=live.tenant_id,
                        lease_id=live.lease_id,
                        owner_workflow_id=self._workflow_id(live),
                        fencing_token=device.fencing_counter,
                        expires_at=live.expires_at,
                        canceled_at=None,
                        owner_type=LEASE_OWNER_REMOTE,
                        created_at=now,
                    )
                )
            else:
                row.owner_type = LEASE_OWNER_REMOTE
                row.owner_workflow_id = self._workflow_id(live)
                row.fencing_token = device.fencing_counter
                row.lease_id = live.lease_id
                row.canceled_at = None
                row.expires_at = live.expires_at
            live.epoch = device.fencing_counter
            live.state = REMOTE
            live.input_watermark = 0
            live.input_times = []
            live.seq_regressions = []
            self._audit(db, live, "take-control", str(actor.user_id))
            return self.view(live)

        return await self._transact(work)

    async def release(self, actor: Actor, sid: str, token: str | None) -> dict[str, Any]:
        async def work(db: Any) -> dict[str, Any]:
            live = self._authenticate(actor, None, sid, token)
            await self._sweep_locked(db, live)
            self._require_open(live)
            if live.state != REMOTE:
                raise ConflictError("LIVE_NOT_REMOTE: only a REMOTE session can be released")
            handover = await self._release_locked(db, live, str(actor.user_id))
            view = self.view(live)
            view["handover"] = handover
            return view

        return await self._transact(work)

    async def _release_locked(
        self, db: Any, live: FleetLiveSession, actor_id: str, *, cause: str = "operator"
    ) -> dict[str, Any]:
        row = await db.get(DeviceLeaseRow, live.device_id)
        # Row may have been replaced by a claim while VIEWING; only downgrade
        # a row this session currently owns.
        if row is not None and row.owner_workflow_id == self._workflow_id(live):
            row.owner_type = LEASE_OWNER_LIVE
        live.state = VIEWING
        affected = await self._affected_tasks(db, live)
        self._audit(
            db,
            live,
            "release",
            actor_id,
            metadata={"cause": cause, "affectedTasks": affected},
        )
        return {
            "from": REMOTE,
            "to": VIEWING,
            "cause": cause,
            "affectedTasks": affected,
            "singleWriterRestored": True,
            "frameDownlinkContinues": True,
            "releasedAt": _utcnow().isoformat(),
            "releasedBy": actor_id,
            "auditEvent": "live.session.release",
        }

    async def _affected_tasks(self, db: Any, live: FleetLiveSession) -> list[dict[str, Any]]:
        rows = list(
            await db.scalars(
                select(MobileTaskRow)
                .where(
                    MobileTaskRow.device_id == live.device_id,
                    MobileTaskRow.business_state == "PAUSED_WAITING_USER",
                    MobileTaskRow.stall_reason == "live remote control",
                )
                .order_by(MobileTaskRow.created_at)
            )
        )
        # K13 §5: tasks sitting in a destructive-confirmation window (open
        # UNKNOWN action ledger rows on the device) must be resumed by
        # explicit human confirmation, never automatically.
        unknown_open = await open_unknown_actions(db, live.tenant_id, live.device_id)
        confirm_required = bool(unknown_open)
        return [
            {
                "taskId": task.id,
                "pauseState": "PAUSED_WAITING_USER",
                "resumeMode": "CONFIRM_REQUIRED" if confirm_required else "REQUEUE_AUTO",
            }
            for task in rows
        ]

    async def stop(self, actor: Actor, sid: str, token: str | None) -> dict[str, Any]:
        async def work(db: Any) -> dict[str, Any]:
            live = self._authenticate(actor, None, sid, token)
            # K13 §6: any operation riding a dead session/token is 410, stop
            # included; the terminal state is observable via GET status only.
            self._require_open(live)
            await self._close_locked(
                db, live, "OPERATOR_STOP", actor_id=str(actor.user_id)
            )
            return self.view(live)

        return await self._transact(work)

    async def _close_locked(
        self,
        db: Any,
        live: FleetLiveSession,
        cause: str,
        *,
        actor_id: str = "system",
    ) -> None:
        if live.closed:
            return
        live.state = CLOSED
        live.closed_cause = cause
        live.closed_at = _utcnow()
        row = await db.get(DeviceLeaseRow, live.device_id)
        if row is not None and row.owner_workflow_id == self._workflow_id(live):
            row.canceled_at = live.closed_at
        self._audit(db, live, "closed", actor_id, metadata={"cause": cause})

    async def status(self, actor: Actor, sid: str, token: str | None) -> dict[str, Any]:
        async with self.lock, self.database.unit_of_work() as db:
            live = self._authenticate(actor, None, sid, token)
            await self._sweep_locked(db, live)
            return self.view(live)

    # ---- disconnect reclamation (K13 §5/§6) ----
    async def notify_disconnect(
        self, actor: Actor, sid: str, token: str | None, who: str
    ) -> dict[str, Any]:
        async def work(db: Any) -> dict[str, Any]:
            live = self._authenticate(actor, None, sid, token)
            await self._sweep_locked(db, live)
            self._require_open(live)
            now_monotonic = time.monotonic()
            if who == "operator":
                live.operator_lost_monotonic = now_monotonic
                live.operator_socket = None
            else:
                live.companion_lost_monotonic = now_monotonic
                live.companion_socket = None
            if live.state == REMOTE:
                # Abnormal handover: drop the remote grant immediately (input
                # channel closes, single writer restored); the session then
                # rides the grace window toward CLOSED.
                await self._release_locked(db, live, "system", cause="disconnect")
            await self._sweep_locked(db, live)
            return self.view(live)

        return await self._transact(work)

    async def _sweep_locked(self, db: Any, live: FleetLiveSession) -> None:
        if live.closed:
            return
        now_monotonic = time.monotonic()
        if now_monotonic - live.established_monotonic > SESSION_HARD_LIMIT_S:
            await self._close_locked(db, live, "TIMEOUT_30M")
            return
        if live.state == REMOTE and now_monotonic - live.last_frame_monotonic > FRAME_STALE_S:
            await self._release_locked(db, live, "system", cause="frame-stall")
        lost_at = min(
            (
                stamp
                for stamp in (live.operator_lost_monotonic, live.companion_lost_monotonic)
                if stamp is not None
            ),
            default=None,
        )
        frame_stalled = now_monotonic - live.last_frame_monotonic > FRAME_STALE_S + FRAME_GRACE_S
        grace_expired = lost_at is not None and now_monotonic - lost_at > FRAME_GRACE_S
        if frame_stalled or grace_expired:
            await self._close_locked(db, live, "DISCONNECT_GRACE_EXPIRED")

    # ---- input channel (authorization layer; transport relays after this) ----
    async def route_input(
        self,
        actor: Actor,
        device_id: str,
        sid: str,
        token: str | None,
        message: dict[str, Any],
    ) -> dict[str, Any]:
        async def work(db: Any) -> dict[str, Any]:
            live = self._authenticate(actor, device_id, sid, token)
            await self._sweep_locked(db, live)
            self._require_open(live)
            epoch = message.get("epoch")
            if epoch is not None and int(epoch) != live.epoch:
                # K13 §2: anything riding an old epoch is refused outright.
                raise ConflictError(
                    f"LIVE_EPOCH_STALE: session epoch is {live.epoch}, got {epoch}"
                )
            now_monotonic = time.monotonic()
            code = live.check_input(message, now_monotonic)
            if code is not None:
                # Rejections are audited and (when the code severs the grant)
                # downgrade the lease row BEFORE the error response leaves —
                # _transact commits this UoW and re-raises afterwards.
                self._audit(
                    db,
                    live,
                    "input",
                    str(actor.user_id),
                    result="REJECTED",
                    metadata={
                        "code": code,
                        "kind": message.get("kind"),
                        "seq": message.get("seq"),
                        "frameSeq": message.get("frameSeq"),
                        "inputWatermark": live.input_watermark,
                        "latestFrameSeq": live.latest_frame_seq,
                    },
                )
                if live.should_drop_remote(code, now_monotonic):
                    await self._release_locked(
                        db, live, "system", cause=f"input-{code.lower()}"
                    )
                self._raise_input_rejection(code, live)
            socket = live.companion_socket
            if socket is None:
                raise ConflictError("LIVE_COMPANION_OFFLINE: no companion transport attached")
            await socket.send_json({"t": "input", **message})
            self._audit(
                db,
                live,
                "input",
                str(actor.user_id),
                metadata={
                    "kind": message.get("kind"),
                    "seq": message.get("seq"),
                    "frameSeq": message.get("frameSeq"),
                    # Metadata only: coordinates never carry frames (K13 §6).
                    "x": message.get("x"),
                    "y": message.get("y"),
                },
            )
            return {
                "accepted": True,
                "inputWatermark": live.input_watermark,
                "latestFrameSeq": live.latest_frame_seq,
            }

        return await self._transact(work)

    def _raise_input_rejection(self, code: str, live: FleetLiveSession) -> None:
        watermark = live.input_watermark
        latest = live.latest_frame_seq
        fields = {"inputWatermark": str(watermark), "latestFrameSeq": str(latest)}
        if code == "LIVE_INPUT_FORBIDDEN":
            raise LiveInputForbiddenError(
                f"input rejected: {code} (watermark={watermark}, latestFrameSeq={latest})",
                fields=fields,
            )
        if code == "INPUT_EXPIRED":
            raise InputExpiredError(
                f"input rejected: {code} (watermark={watermark}, latestFrameSeq={latest})",
                fields=fields,
            )
        if code == "INPUT_SEQ_REGRESSION":
            raise InputSeqRegressionError(
                f"input rejected: {code} (watermark={watermark}, latestFrameSeq={latest})",
                fields=fields,
            )
        if code == "LIVE_RATE_LIMITED":
            raise LiveRateLimitedError(
                f"input rejected: {code} (watermark={watermark}, latestFrameSeq={latest})",
                fields=fields,
            )
        raise ConflictError(f"input rejected: {code}")

    # ---- transport relay hooks (edge adapters call these) ----
    def note_frame(self, sid: str, frame_seq: int) -> None:
        live = self.sessions.get(sid)
        if live is None or live.closed:
            return
        now_monotonic = time.monotonic()
        live.latest_frame_seq = max(live.latest_frame_seq, int(frame_seq))
        live.frame_delivered_at[int(frame_seq)] = now_monotonic
        live.last_frame_monotonic = now_monotonic
        if len(live.frame_delivered_at) > 128:
            for old_seq in sorted(live.frame_delivered_at)[:-128]:
                live.frame_delivered_at.pop(old_seq, None)

    def attach_companion(self, sid: str, socket: Any) -> FleetLiveSession:
        live = self.sessions.get(sid)
        if live is None:
            raise NotFoundError("live session was not found")
        live.companion_socket = socket
        live.companion_lost_monotonic = None
        return live

    # ---- view ----
    def view(self, live: FleetLiveSession, *, include_token: bool = False) -> dict[str, Any]:
        spec = live.tier_spec
        payload: dict[str, Any] = {
            "sessionId": live.sid,
            "tenantId": live.tenant_id,
            "deviceId": live.device_id,
            "operatorId": live.operator_id,
            "tier": spec.tier,
            "transport": spec.transport,
            "state": live.state,
            "lease": {
                "deviceLeaseId": live.lease_id,
                "epoch": live.epoch,
                "purpose": "LIVE",
            },
            "capabilities": {
                "allowsInput": spec.allows_input,
                "uiLabel": spec.ui_label,
                "frameDownlink": True,
                "turnRequired": spec.turn_required,
            },
            "authorization": {
                "mediaProjectionRequired": True,
                "userConfirmedAt": (
                    live.authorization_confirmed_at.isoformat()
                    if live.authorization_confirmed_at
                    else None
                ),
                "persistsAcrossReboot": False,
                "silentResumeAllowed": False,
            },
            "frameGeometry": dict(DEFAULT_FRAME_GEOMETRY),
            "establishedAt": live.established_at.isoformat(),
            "expiresAt": live.expires_at.isoformat(),
            "maxDurationMinutes": SESSION_HARD_LIMIT_S // 60,
            "gates": list(spec.gates),
            "transportPlan": {
                "kind": live.transport_plan.kind,
                "turnRequired": live.transport_plan.turn_required,
                "details": live.transport_plan.details,
            },
        }
        if spec.input_policy is not None:
            payload["inputPolicy"] = dict(spec.input_policy)
        if live.closed:
            payload["terminal"] = {
                "cause": live.closed_cause,
                "resumable": False,
                "reauthorizationRequired": True,
                "tokenInvalidated": True,
                "closedAt": live.closed_at.isoformat() if live.closed_at else None,
            }
        if include_token:
            payload["sessionToken"] = live.token
        return payload


# ---------------------------------------------------------------------------
# Routes (single router: operator surface + companion ack)
# ---------------------------------------------------------------------------


class FleetLiveEstablishRequest(BaseModel):
    tier: str
    transport: str | None = None


class FleetLiveAckRequest(BaseModel):
    granted: bool
    confirmedAt: datetime | None = None


class FleetLiveDisconnectRequest(BaseModel):
    who: str = Field(pattern="^(operator|companion)$")


class FleetLiveInputRequest(BaseModel):
    kind: Literal["tap", "swipe", "text"]
    seq: int = Field(ge=1)
    frameSeq: int = Field(ge=1)
    epoch: int | None = None
    x: float | None = Field(default=None, ge=0)
    y: float | None = Field(default=None, ge=0)
    x2: float | None = Field(default=None, ge=0)
    y2: float | None = Field(default=None, ge=0)
    text: str | None = Field(default=None, max_length=500)


fleet_live_router = APIRouter(tags=["fleet-live"])


def _service(request: Request) -> FleetLiveService:
    service = request.app.state.fleet_live_service
    assert isinstance(service, FleetLiveService)
    return service


ServiceDep = Annotated[FleetLiveService, Depends(_service)]
ActorDep = Annotated[Actor, Depends(current_actor)]
TokenDep = Annotated[
    str | None, Header(alias=SESSION_TOKEN_HEADER)
]


@fleet_live_router.post(
    "/api/v1/live/devices/{device_id}/sessions", status_code=201
)
async def establish_fleet_live_session(
    device_id: str,
    body: FleetLiveEstablishRequest,
    actor: ActorDep,
    service: ServiceDep,
) -> dict[str, Any]:
    return await service.establish(actor, device_id, body.tier, body.transport)


@fleet_live_router.get("/api/v1/live/sessions/{sid}")
async def fleet_live_session_status(
    sid: str, actor: ActorDep, service: ServiceDep, token: TokenDep = None
) -> dict[str, Any]:
    return await service.status(actor, sid, token)


@fleet_live_router.post("/api/v1/live/sessions/{sid}:take-control")
async def fleet_live_take_control(
    sid: str, actor: ActorDep, service: ServiceDep, token: TokenDep = None
) -> dict[str, Any]:
    return await service.take_control(actor, sid, token)


@fleet_live_router.post("/api/v1/live/sessions/{sid}:release")
async def fleet_live_release(
    sid: str, actor: ActorDep, service: ServiceDep, token: TokenDep = None
) -> dict[str, Any]:
    return await service.release(actor, sid, token)


@fleet_live_router.post("/api/v1/live/sessions/{sid}:stop")
async def fleet_live_stop(
    sid: str, actor: ActorDep, service: ServiceDep, token: TokenDep = None
) -> dict[str, Any]:
    return await service.stop(actor, sid, token)


@fleet_live_router.post("/api/v1/live/sessions/{sid}/disconnect")
async def fleet_live_disconnect(
    sid: str,
    body: FleetLiveDisconnectRequest,
    actor: ActorDep,
    service: ServiceDep,
    token: TokenDep = None,
) -> dict[str, Any]:
    return await service.notify_disconnect(actor, sid, token, body.who)


@fleet_live_router.post("/api/v1/live/devices/{device_id}/sessions/{sid}/input")
async def fleet_live_input(
    device_id: str,
    sid: str,
    body: FleetLiveInputRequest,
    actor: ActorDep,
    service: ServiceDep,
    token: TokenDep = None,
) -> dict[str, Any]:
    return await service.route_input(
        actor, device_id, sid, token, body.model_dump(exclude_none=True)
    )


@fleet_live_router.post("/companion/v2/fleet-live/{sid}/ack")
async def fleet_live_ack(
    sid: str, body: FleetLiveAckRequest, binding: Binding, service: ServiceDep
) -> dict[str, Any]:
    return await service.ack_projection(
        tenant_id=str(binding.tenant_id),
        device_id=binding.device_id,
        sid=sid,
        granted=body.granted,
        confirmed_at=body.confirmedAt,
    )
