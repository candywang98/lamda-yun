"""Remote live session slice 1 (p10-live/20260913.1).

Server-authoritative VIEWING/REMOTE/CLOSED state machine, in-memory frame relay
over two WebSockets, single-writer protection for task claims. Frames are never
persisted; audits record metadata only. WebRTC/TURN (D03) is a later transport
upgrade — session semantics here are transport-independent.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from cloudctl_domain import Actor, AuthenticationError, ConflictError, NotFoundError
from fastapi import APIRouter, Depends, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from sqlalchemy import update

from .auth import current_actor
from .db import AuditEventRow, MobileBindingRow, MobileTaskRow
from .mobile_service import MobileTaskService, _now

VIEWING = "VIEWING"
REMOTE = "REMOTE"
CLOSED = "CLOSED"
SESSION_HARD_LIMIT_S = 30 * 60
FRAME_STALE_S = 30.0
FRAME_GRACE_S = 10.0
INPUT_RATE_PER_S = 10


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


class LiveSession:
    def __init__(self, sid: str, device_id: str, tenant_id: str) -> None:
        self.sid = sid
        self.device_id = device_id
        self.tenant_id = tenant_id
        self.state = VIEWING
        self.opened_monotonic = time.monotonic()
        self.last_frame_monotonic = time.monotonic()
        self.input_seq = 0
        self.input_times: list[float] = []
        self.operator_socket: WebSocket | None = None
        self.companion_socket: WebSocket | None = None

    # ---- pure checks (unit-testable) ----
    def is_expired(self, now_monotonic: float) -> str | None:
        if self.state == CLOSED:
            return None
        if now_monotonic - self.opened_monotonic > SESSION_HARD_LIMIT_S:
            return "TIMEOUT"
        if now_monotonic - self.last_frame_monotonic > FRAME_STALE_S + FRAME_GRACE_S:
            return "FRAME_STALLED"
        return None

    def check_input(self, kind: str, seq: int, now_monotonic: float) -> str | None:
        if self.state != REMOTE:
            return "NOT_REMOTE"
        if kind not in ("tap", "swipe", "text"):
            return "BAD_KIND"
        if seq <= self.input_seq:
            return "SEQ_STALE"
        self.input_times = [stamp for stamp in self.input_times if now_monotonic - stamp < 1.0]
        if len(self.input_times) >= INPUT_RATE_PER_S:
            return "RATE_EXCEEDED"
        self.input_times.append(now_monotonic)
        self.input_seq = seq
        return None


class LiveService:
    """In-memory registry; one live session per device at a time."""

    def __init__(self, mobile: MobileTaskService) -> None:
        self.mobile = mobile
        self.database = mobile.database
        self.sessions: dict[str, LiveSession] = {}
        self.by_device: dict[str, str] = {}
        self.lock = asyncio.Lock()

    def _audit(self, session: Any, live: LiveSession, kind: str, actor_id: str) -> None:
        session.add(
            AuditEventRow(
                id=str(uuid.uuid4()),
                tenant_id=live.tenant_id,
                actor_id=actor_id,
                actor_type="operator",
                resource_type="live_session",
                resource_id=live.sid,
                request_id=str(uuid.uuid4()),
                device_id=live.device_id,
                action=f"live.session.{kind}",
                metadata_json={"state": live.state},
                occurred_at=_now(),
                result="SUCCESS",
            )
        )

    async def _sweep_locked(
        self, live: LiveSession, session: Any, actor_id: str = "system"
    ) -> None:
        reason = live.is_expired(time.monotonic())
        if reason and live.state != CLOSED:
            live.state = CLOSED
            self.by_device.pop(live.device_id, None)
            self._audit(session, live, f"close.{reason.lower()}", actor_id)

    async def open_session(self, actor: Actor, device_id: str) -> dict[str, Any]:
        now_monotonic = time.monotonic()
        async with self.lock, self.database.unit_of_work() as session:
            existing_id = self.by_device.get(device_id)
            if existing_id:
                live = self.sessions.get(existing_id)
                if live and live.is_expired(now_monotonic) is None:
                    raise ConflictError("SESSION_EXISTS")
            live = LiveSession(str(uuid.uuid4()), device_id, str(actor.tenant_id))
            self.sessions[live.sid] = live
            self.by_device[device_id] = live.sid
            self._audit(session, live, "open", str(actor.user_id))
            return self.view(live)

    def view(self, live: LiveSession) -> dict[str, Any]:
        age = int(time.monotonic() - live.opened_monotonic)
        return {
            "sessionId": live.sid,
            "deviceId": live.device_id,
            "state": live.state,
            "ageSeconds": age,
            "remainingSeconds": max(0, SESSION_HARD_LIMIT_S - age),
        }

    def session_for(self, actor: Actor, sid: str) -> LiveSession:
        live = self.sessions.get(sid)
        if live is None or live.tenant_id != str(actor.tenant_id):
            raise NotFoundError("live session was not found")
        return live

    async def status(self, actor: Actor, sid: str) -> dict[str, Any]:
        async with self.lock, self.database.unit_of_work() as session:
            live = self.session_for(actor, sid)
            await self._sweep_locked(live, session)
            return self.view(live)

    async def take_control(self, actor: Actor, sid: str) -> dict[str, Any]:
        async with self.lock, self.database.unit_of_work() as session:
            live = self.session_for(actor, sid)
            await self._sweep_locked(live, session, str(actor.user_id))
            if live.state == CLOSED:
                raise ConflictError("SESSION_CLOSED")
            if live.state == REMOTE:
                return self.view(live)
            live.state = REMOTE
            live.input_seq = 0
            live.input_times = []
            # Single writer: force the device's running task into the operator lane.
            await session.execute(
                update(MobileTaskRow)
                .where(
                    MobileTaskRow.device_id == live.device_id,
                    MobileTaskRow.business_state == "RUNNING",
                )
                .values(business_state="PAUSED_WAITING_USER", stall_reason="live remote control")
            )
            self._audit(session, live, "take-control", str(actor.user_id))
            await self._broadcast_state(live)
            return self.view(live)

    async def release(self, actor: Actor, sid: str) -> dict[str, Any]:
        async with self.lock, self.database.unit_of_work() as session:
            live = self.session_for(actor, sid)
            if live.state == CLOSED:
                raise ConflictError("SESSION_CLOSED")
            live.state = VIEWING
            self._audit(session, live, "release", str(actor.user_id))
            await self._broadcast_state(live)
            return self.view(live)

    async def stop(self, actor: Actor, sid: str) -> dict[str, Any]:
        async with self.lock, self.database.unit_of_work() as session:
            live = self.session_for(actor, sid)
            live.state = CLOSED
            self.by_device.pop(live.device_id, None)
            self._audit(session, live, "close.manual", str(actor.user_id))
            await self._broadcast_state(live)
            return self.view(live)

    def has_remote(self, device_id: str) -> bool:
        sid = self.by_device.get(device_id)
        if not sid:
            return False
        live = self.sessions.get(sid)
        return live is not None and live.state == REMOTE

    # ---- WS helpers (thin, not unit-tested) ----
    async def attach_operator(self, actor: Actor, sid: str, socket: WebSocket) -> LiveSession:
        live = self.session_for(actor, sid)
        live.operator_socket = socket
        return live

    async def attach_companion(self, device_id: str, sid: str, socket: WebSocket) -> LiveSession:
        live = self.sessions.get(sid)
        if live is None or live.device_id != device_id:
            raise NotFoundError("live session was not found")
        live.companion_socket = socket
        return live

    async def discover_for_device(self, device_id: str) -> dict[str, Any]:
        """WIRE3: companion session discovery — the device polls this on its
        heartbeat cadence; 404 means "no live session", any active session for
        the device is returned exactly once per poll."""
        async with self.lock, self.database.unit_of_work() as session:
            sid = self.by_device.get(device_id)
            live = self.sessions.get(sid) if sid else None
            if live is None:
                raise NotFoundError("no live session for device")
            await self._sweep_locked(live, session, device_id)
            if live.state == CLOSED:
                raise NotFoundError("no live session for device")
            return self.view(live)

    async def projection_ack(
        self, device_id: str, sid: str, granted: bool
    ) -> dict[str, Any]:
        """WIRE3: the MediaProjection user-confirmation result for one session.
        A denial is terminal: the session closes and the operator panel learns
        via the state push."""
        async with self.lock, self.database.unit_of_work() as session:
            live = self.sessions.get(sid)
            if live is None or live.device_id != device_id:
                raise NotFoundError("live session was not found")
            if live.state == CLOSED:
                raise ConflictError("SESSION_CLOSED")
            self._audit(
                session,
                live,
                "projection-ack" if granted else "projection-denied",
                device_id,
            )
            if not granted:
                live.state = CLOSED
                self.by_device.pop(live.device_id, None)
                await self._broadcast_state(live)
            return {"ok": True, "sessionId": live.sid, "state": live.state}

    async def note_frame(self, live: LiveSession, jpeg_b64: str) -> None:
        live.last_frame_monotonic = time.monotonic()
        socket = live.operator_socket
        if socket is not None:
            await socket.send_json({"t": "frame", "jpeg": jpeg_b64})

    async def route_input(self, live: LiveSession, message: dict[str, Any]) -> None:
        error = live.check_input(
            str(message.get("kind", "")), int(message.get("seq", 0)), time.monotonic()
        )
        if error:
            if error in ("RATE_EXCEEDED", "SEQ_STALE"):
                live.state = VIEWING
                await self._broadcast_state(live)
                raise ConflictError(f"LIVE_INPUT_{error}")
            raise ConflictError(f"LIVE_INPUT_{error}")
        socket = live.companion_socket
        if socket is None:
            raise ConflictError("LIVE_COMPANION_OFFLINE")
        await socket.send_json({"t": "input", **message})

    async def _broadcast_state(self, live: LiveSession) -> None:
        socket = live.operator_socket
        if socket is not None:
            await socket.send_json({"t": "state", "state": live.state})
        # WIRE3: the companion mirrors the server state machine (its remote
        # input gate rejects everything while not REMOTE), so state changes
        # must reach the device link too — not only the operator panel.
        companion = live.companion_socket
        if companion is not None:
            await companion.send_json({"t": "state", "state": live.state})


operator_router = APIRouter(prefix="/api/v1/devices/{device_id}/live", tags=["live-operator"])
companion_router = APIRouter(prefix="/companion/v2/live", tags=["live-companion"])

def _service(request: Request) -> LiveService:
    service = request.app.state.live_service
    assert isinstance(service, LiveService)
    return service




ServiceDep = Annotated[LiveService, Depends(_service)]
ActorDep = Annotated[Actor, Depends(current_actor)]


@operator_router.post("")
async def open_live(
    device_id: str, actor: ActorDep, live_service: ServiceDep
) -> dict[str, Any]:
    return await live_service.open_session(actor, device_id)


@operator_router.get("/{sid}")
async def live_status(sid: str, actor: ActorDep, live_service: ServiceDep) -> dict[str, Any]:
    return await live_service.status(actor, sid)


@operator_router.post("/{sid}:take-control")
async def take_control(sid: str, actor: ActorDep, live_service: ServiceDep) -> dict[str, Any]:
    return await live_service.take_control(actor, sid)


@operator_router.post("/{sid}:release")
async def release(sid: str, actor: ActorDep, live_service: ServiceDep) -> dict[str, Any]:
    return await live_service.release(actor, sid)


@operator_router.post("/{sid}:stop")
async def stop(sid: str, actor: ActorDep, live_service: ServiceDep) -> dict[str, Any]:
    return await live_service.stop(actor, sid)


@operator_router.websocket("/{sid}/stream")
async def operator_stream(
    sid: str,
    websocket: WebSocket,
    live_service: ServiceDep,
) -> None:
    await websocket.accept()
    live = live_service.sessions.get(sid)
    if live is None:
        await websocket.send_json({"t": "state", "state": CLOSED})
        await websocket.close()
        return
    live.operator_socket = websocket
    await websocket.send_json({"t": "state", "state": live.state})
    try:
        while True:
            message = await websocket.receive_json()
            if message.get("t") != "input":
                continue
            try:
                await live_service.route_input(live, message)
            except ConflictError:
                await websocket.send_json({"t": "state", "state": live.state})
    except WebSocketDisconnect:
        live.operator_socket = None


@companion_router.websocket("/{sid}")
async def companion_stream(
    sid: str,
    websocket: WebSocket,
    live_service: ServiceDep,
) -> None:
    # Companion auth: the binding token is validated on the first frame exchange
    # via /ack before any input flows; the WS itself is device-scoped by sid.
    await websocket.accept()
    live = next(
        (item for item in live_service.sessions.values() if item.sid == sid),
        None,
    )
    if live is None:
        await websocket.close()
        return
    live.companion_socket = websocket
    try:
        while True:
            message = await websocket.receive_json()
            if message.get("t") == "frame":
                await live_service.note_frame(live, str(message.get("jpeg", "")))
            elif message.get("t") == "state":
                await live_service._broadcast_state(live)
    except WebSocketDisconnect:
        live.companion_socket = None


async def _companion_binding(request: Request, live_service: ServiceDep) -> MobileBindingRow:
    scheme, separator, token = request.headers.get("Authorization", "").partition(" ")
    if separator != " " or scheme.lower() != "bearer" or not token:
        raise AuthenticationError("Companion bearer authentication is required")
    return await live_service.mobile.authenticate(token)


CompanionBinding = Annotated[MobileBindingRow, Depends(_companion_binding)]


class LiveAckRequest(BaseModel):
    granted: bool


@companion_router.get("/session")
async def companion_live_session(
    binding: CompanionBinding, live_service: ServiceDep
) -> dict[str, Any]:
    """WIRE3 (Q14): the device-side poll that LiveSessionController.checkForSession
    expects — returns the active session for this device or 404."""
    return await live_service.discover_for_device(binding.device_id)


@companion_router.post("/{sid}/ack")
async def companion_live_ack(
    sid: str,
    body: LiveAckRequest,
    binding: CompanionBinding,
    live_service: ServiceDep,
) -> dict[str, Any]:
    """WIRE3 (Q14): MediaProjection user-confirmation result for one session."""
    return await live_service.projection_ack(binding.device_id, sid, body.granted)
