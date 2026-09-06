from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import secrets
import threading
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from cloudctl_edge_protocol import edge_control_pb2 as pb


class DebugSessionError(PermissionError):
    pass


@dataclass(frozen=True, slots=True)
class ProxyTarget:
    host: str
    port: int = 65000

    def __post_init__(self) -> None:
        address = ipaddress.ip_address(self.host)
        if not (address.is_private or address.is_loopback):
            raise DebugSessionError("debug target must be inside the device network")
        if self.port != 65000:
            raise DebugSessionError("remote proxy only targets the configured LAMDA service")


@dataclass(slots=True)
class _Session:
    session_id: str
    device_id: str
    expires_at: datetime
    capabilities: frozenset[str]
    token_digest: str
    target: ProxyTarget
    lease_id: str | None = None
    fencing_token: int | None = None
    revoked: bool = False


class DebugSessionManager:
    # Keep this set in lock-step with Control API and Studio.  Broad aliases such as
    # ``view`` or ``input`` are intentionally not accepted.
    ALLOWED_CAPABILITIES = frozenset(
        {
            "view.frame",
            "view.layout",
            "input.tap",
            "input.swipe",
            "input.text",
            "debug.steps",
            "debug.variables",
            "evidence.capture",
        }
    )
    MAX_TTL = timedelta(minutes=15)
    _COMPAT_ALIASES = {"view": "view.frame", "layout": "view.layout", "input": "input.tap"}

    def __init__(self) -> None:
        self._sessions: dict[str, _Session] = {}
        self._lock = threading.Lock()

    def grant(
        self,
        *,
        session_id: str,
        device_id: str,
        expires_at: datetime,
        capabilities: set[str],
        target: ProxyTarget,
        bearer_token: str | None = None,
        lease_id: str | None = None,
        fencing_token: int | None = None,
        now: datetime | None = None,
    ) -> str:
        issued_at = now or datetime.now(UTC)
        if expires_at.tzinfo is None:
            raise DebugSessionError("debug expiry must be timezone aware")
        if expires_at <= issued_at or expires_at - issued_at > self.MAX_TTL:
            raise DebugSessionError("debug grant lifetime is invalid")
        normalized = {self._COMPAT_ALIASES.get(value, value) for value in capabilities}
        if not normalized or not normalized <= self.ALLOWED_CAPABILITIES:
            raise DebugSessionError("debug grant contains a prohibited capability")
        token = bearer_token or secrets.token_urlsafe(32)
        if len(token) < 32:
            raise DebugSessionError("debug bearer token does not have enough entropy")
        if lease_id is not None and not lease_id:
            raise DebugSessionError("debug lease_id cannot be empty")
        if fencing_token is not None and fencing_token < 1:
            raise DebugSessionError("debug fencing token must be positive")
        session = _Session(
            session_id=session_id,
            device_id=device_id,
            expires_at=expires_at,
            capabilities=frozenset(normalized),
            token_digest=self._digest(token),
            target=target,
            lease_id=lease_id,
            fencing_token=fencing_token,
        )
        with self._lock:
            existing = self._sessions.get(session_id)
            if existing is not None:
                if existing == session:
                    return token
                raise DebugSessionError("debug session already exists with different content")
            self._sessions[session_id] = session
        return token

    def authorize(
        self,
        *,
        session_id: str,
        device_id: str,
        token: str,
        capability: str,
        now: datetime | None = None,
    ) -> ProxyTarget:
        checked_at = now or datetime.now(UTC)
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None or session.revoked:
                raise DebugSessionError("debug session is not active")
            if session.device_id != device_id:
                raise DebugSessionError("debug session belongs to another device")
            if checked_at >= session.expires_at:
                session.revoked = True
                raise DebugSessionError("debug session expired")
            capability = self._COMPAT_ALIASES.get(capability, capability)
            if capability not in session.capabilities:
                raise DebugSessionError("capability was not granted")
            if not secrets.compare_digest(session.token_digest, self._digest(token)):
                raise DebugSessionError("invalid debug token")
            return session.target

    def revoke(self, session_id: str) -> None:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is not None:
                session.revoked = True

    def validate_frame(
        self,
        frame: pb.DebugRelayFrame,
        *,
        device_id: str,
        now: datetime | None = None,
    ) -> None:
        """Validate a hub-authenticated frame before handing it to the device proxy.

        The bearer is intentionally absent from relay frames. The mTLS Edge stream
        authenticates the hub; this check still binds every frame to the exact
        device/session and capability granted at the Edge.
        """
        checked_at = now or datetime.now(UTC)
        with self._lock:
            session = self._sessions.get(frame.session_id)
            if session is None or session.revoked:
                raise DebugSessionError("debug session is not active")
            if session.device_id != device_id:
                raise DebugSessionError("debug frame belongs to another device")
            if checked_at >= session.expires_at:
                session.revoked = True
                raise DebugSessionError("debug session expired")
            capability = self._COMPAT_ALIASES.get(frame.capability, frame.capability)
            if capability not in session.capabilities:
                raise DebugSessionError("capability was not granted")
            if frame.kind not in {
                "tap",
                "swipe",
                "text",
                "evidence.request",
                "ack",
                "frame",
                "layout",
                "ready",
                "error",
            }:
                raise DebugSessionError("debug frame kind is not allowed")
            if len(frame.payload) > 256 * 1024:
                raise DebugSessionError("debug frame payload exceeds limit")

    def expire(self, *, now: datetime | None = None) -> int:
        """Mark elapsed grants inactive; returns the number of sessions changed."""
        checked_at = now or datetime.now(UTC)
        changed = 0
        with self._lock:
            for session in self._sessions.values():
                if not session.revoked and checked_at >= session.expires_at:
                    session.revoked = True
                    changed += 1
        return changed

    @staticmethod
    def _digest(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()


TargetConnector = Callable[
    [ProxyTarget], Awaitable[tuple[asyncio.StreamReader, asyncio.StreamWriter]]
]


class DebugRelay:
    """Relays an authorized session without disclosing target network or certificate material."""

    def __init__(
        self,
        sessions: DebugSessionManager,
        connector: TargetConnector,
        *,
        idle_timeout_seconds: float = 30,
        max_bytes_per_direction: int = 256 * 1024 * 1024,
    ):
        self._sessions = sessions
        self._connector = connector
        self._idle_timeout_seconds = idle_timeout_seconds
        self._max_bytes_per_direction = max_bytes_per_direction

    async def relay(
        self,
        client_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
        *,
        session_id: str,
        device_id: str,
        token: str,
        capability: str,
    ) -> None:
        target = self._sessions.authorize(
            session_id=session_id,
            device_id=device_id,
            token=token,
            capability=capability,
        )
        upstream_reader, upstream_writer = await self._connector(target)
        try:
            downstream = asyncio.create_task(
                self._copy(client_reader, upstream_writer), name=f"debug-up:{session_id}"
            )
            upstream = asyncio.create_task(
                self._copy(upstream_reader, client_writer), name=f"debug-down:{session_id}"
            )
            done, pending = await asyncio.wait(
                {downstream, upstream}, return_when=asyncio.FIRST_COMPLETED
            )
            for task in pending:
                task.cancel()
            await asyncio.gather(*done, *pending, return_exceptions=True)
        finally:
            upstream_writer.close()
            client_writer.close()
            await asyncio.gather(
                upstream_writer.wait_closed(), client_writer.wait_closed(), return_exceptions=True
            )

    async def _copy(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        transferred = 0
        while True:
            try:
                chunk = await asyncio.wait_for(
                    reader.read(64 * 1024), timeout=self._idle_timeout_seconds
                )
            except TimeoutError as exc:
                raise DebugSessionError("debug relay idle timeout") from exc
            if not chunk:
                return
            transferred += len(chunk)
            if transferred > self._max_bytes_per_direction:
                raise DebugSessionError("debug relay byte budget exceeded")
            writer.write(chunk)
            await writer.drain()
