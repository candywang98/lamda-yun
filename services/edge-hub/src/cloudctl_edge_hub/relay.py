"""Capability-bound browser relay routing over the outbound Edge stream.

The hub never opens a connection to a device.  A browser connection is
authenticated against a short-lived grant, then frames are queued onto the
already mTLS-authenticated Edge stream.  Only bounded application frames are
accepted; this module intentionally has no shell, ADB, or arbitrary socket API.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime

from cloudctl_edge_protocol import edge_control_pb2 as pb

from .session import EdgeHub, SessionError

MAX_PAYLOAD = 256 * 1024
ALLOWED_KINDS = frozenset(
    {"tap", "swipe", "text", "evidence.request", "ack", "frame", "layout", "ready", "error"}
)
ALLOWED_CAPABILITIES = frozenset(
    {"input.tap", "input.swipe", "input.text", "evidence.capture", "view.frame", "view.layout"}
)


@dataclass(frozen=True, slots=True)
class RelayGrant:
    session_id: str
    edge_id: str
    device_id: str
    capabilities: frozenset[str]
    expires_at: datetime
    token_digest: str
    revoked: bool = False


class RelayConnection:
    """An authenticated browser-side handle; token is not retained."""

    def __init__(self, router: RelayRouter, grant: RelayGrant):
        self._router = router
        self.grant = grant
        self.incoming: asyncio.Queue[pb.DebugRelayFrame] = asyncio.Queue(maxsize=64)
        self.closed = False

    async def send(self, *, request_id: str, kind: str, capability: str, payload: object) -> None:
        if self.closed:
            raise SessionError("relay connection is closed")
        await self._router.from_browser(
            self.grant,
            pb.DebugRelayFrame(
                session_id=self.grant.session_id,
                device_id=self.grant.device_id,
                request_id=request_id,
                kind=kind,
                capability=capability,
                payload=_encode_payload(payload),
            ),
        )

    async def receive(self) -> pb.DebugRelayFrame:
        if self.closed:
            raise SessionError("relay connection is closed")
        return await self.incoming.get()

    def close(self) -> None:
        self.closed = True


class RelayRouter:
    """Routes browser frames to one Edge and Edge replies to one browser."""

    def __init__(self, hub: EdgeHub):
        self._hub = hub
        self._grants: dict[str, RelayGrant] = {}
        self._connections: dict[str, RelayConnection] = {}
        self._lock = asyncio.Lock()
        hub.on_edge_message(self._on_edge_message)

    async def register(self, grant: RelayGrant) -> None:
        if not grant.session_id or not grant.edge_id or not grant.device_id:
            raise SessionError("relay grant binding is incomplete")
        if not grant.capabilities <= ALLOWED_CAPABILITIES:
            raise SessionError("relay grant contains a prohibited capability")
        expiry = _aware(grant.expires_at)
        if expiry <= datetime.now(UTC):
            raise SessionError("relay grant is expired")
        async with self._lock:
            existing = self._grants.get(grant.session_id)
            if existing is not None and existing != grant:
                raise SessionError("relay grant already exists with different binding")
            self._grants[grant.session_id] = grant

    async def authenticate(self, *, session_id: str, token: str) -> RelayConnection:
        if len(token) < 32 or len(token) > 256:
            raise SessionError("relay token has invalid length")
        async with self._lock:
            grant = self._grants.get(session_id)
            if grant is None or grant.revoked or _aware(grant.expires_at) <= datetime.now(UTC):
                raise SessionError("relay session is not active")
            if not hmac.compare_digest(grant.token_digest, _digest(token)):
                raise SessionError("invalid relay token")
            connection = RelayConnection(self, grant)
            old = self._connections.get(session_id)
            if old is not None:
                old.close()
            self._connections[session_id] = connection
            return connection

    async def revoke(self, session_id: str) -> None:
        async with self._lock:
            grant = self._grants.get(session_id)
            if grant is not None:
                self._grants[session_id] = replace(grant, revoked=True)
            connection = self._connections.pop(session_id, None)
            if connection is not None:
                connection.close()

    async def from_browser(self, grant: RelayGrant, frame: pb.DebugRelayFrame) -> None:
        self._validate_frame(frame, grant)
        # Re-check the grant binding at send time, so revocation closes a race
        # between authentication and a subsequent browser frame.
        async with self._lock:
            current = self._grants.get(grant.session_id)
            if current != grant or grant.revoked or _aware(grant.expires_at) <= datetime.now(UTC):
                raise SessionError("relay session is no longer active")
        await self._hub.queue(
            grant.edge_id,
            pb.CloudToEdge(relay_frame=frame),
        )

    async def _on_edge_message(self, edge_id: str, message: pb.EdgeToCloud) -> None:
        if message.WhichOneof("body") != "relay_frame":
            return
        frame = message.relay_frame
        async with self._lock:
            grant = self._grants.get(frame.session_id)
            connection = self._connections.get(frame.session_id)
            if (
                grant is None
                or connection is None
                or connection.closed
                or grant.revoked
                or grant.edge_id != edge_id
                or _aware(grant.expires_at) <= datetime.now(UTC)
            ):
                return
            self._validate_frame(frame, grant)
            try:
                connection.incoming.put_nowait(frame)
            except asyncio.QueueFull as exc:
                connection.close()
                raise SessionError("relay browser queue is full") from exc

    @staticmethod
    def _validate_frame(frame: pb.DebugRelayFrame, grant: RelayGrant) -> None:
        if frame.session_id != grant.session_id:
            raise SessionError("relay frame session binding mismatch")
        if not frame.request_id or len(frame.request_id) > 128:
            raise SessionError("relay request id is invalid")
        if frame.kind not in ALLOWED_KINDS:
            raise SessionError("relay frame kind is not allowed")
        if frame.capability not in grant.capabilities:
            raise SessionError("relay frame capability was not granted")
        if len(frame.payload) > MAX_PAYLOAD:
            raise SessionError("relay frame payload exceeds limit")


def relay_grant_from_token(
    *,
    session_id: str,
    edge_id: str,
    device_id: str,
    capabilities: list[str],
    expires_at: datetime,
    token: str,
) -> RelayGrant:
    if not token:
        raise SessionError("relay token is required")
    return RelayGrant(
        session_id=session_id,
        edge_id=edge_id,
        device_id=device_id,
        capabilities=frozenset(capabilities),
        expires_at=_aware(expires_at),
        token_digest=_digest(token),
    )


def _encode_payload(payload: object) -> bytes:
    try:
        encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode()
    except (TypeError, ValueError) as exc:
        raise SessionError("relay payload must be JSON serializable") from exc
    if len(encoded) > MAX_PAYLOAD:
        raise SessionError("relay frame payload exceeds limit")
    return encoded


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()
