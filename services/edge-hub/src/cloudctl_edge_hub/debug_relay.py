"""Authenticated browser Debug WebSocket ingress.

The browser side of a debug session is deliberately a small JSON protocol.  It
does not expose ADB, shell, Frida, or a raw device socket.  Commands are
adapted to the existing outbound Edge stream as ``StartCommand`` messages and
therefore retain the normal lease and fencing guarantees.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import secrets
import ssl
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from cloudctl_edge_protocol import edge_control_pb2 as pb
from websockets.exceptions import ConnectionClosedOK

from .debug_delivery import ALLOWED_DEBUG_CAPABILITIES, DebugDeliveryStore
from .session import EdgeHub, SessionError

LOGGER = logging.getLogger("cloudctl.edge_hub.debug_relay")

AUTH_TYPE = "debug.auth"
ALLOWED_MESSAGE_TYPES = ALLOWED_DEBUG_CAPABILITIES
ALLOWED_EDGE_EVENT_TYPES = frozenset(
    {
        "frame",
        "layout",
        "evidence",
        "debug.ack",
    }
)
_CLOSE_UNAUTHENTICATED = 4401
_CLOSE_FORBIDDEN = 4403
_CLOSE_POLICY = 4408
_CLOSE_TOO_LARGE = 1009


class DebugRelayError(ValueError):
    """A protocol or policy violation safe to expose without secret details."""


class WebSocketLike(Protocol):
    request: Any

    async def recv(self) -> str | bytes: ...
    async def send(self, data: str) -> Awaitable[None] | None: ...
    async def close(self, code: int = 1000, reason: str = "") -> Awaitable[None] | None: ...


class RelayTransport(Protocol):
    async def send_command(
        self,
        *,
        session_id: str,
        device_id: str,
        edge_id: str,
        capability: str,
        payload: Mapping[str, object],
        lease_id: str,
        fencing_token: int,
    ) -> str: ...


@dataclass(frozen=True, slots=True)
class DebugRelayConfig:
    origins: tuple[str, ...]
    max_connections: int = 32
    max_message_bytes: int = 256 * 1024
    max_inbound_bytes: int = 4 * 1024 * 1024
    max_outbound_bytes: int = 16 * 1024 * 1024
    max_messages_per_second: int = 20
    idle_timeout_seconds: float = 90.0

    def __post_init__(self) -> None:
        if not self.origins:
            raise ValueError("at least one WebSocket Origin must be allowlisted")
        if any(not origin or origin == "*" for origin in self.origins):
            raise ValueError("wildcard or empty WebSocket Origin is forbidden")
        if self.max_connections < 1 or self.max_message_bytes < 1024:
            raise ValueError("invalid relay limits")
        if self.max_messages_per_second < 1 or self.idle_timeout_seconds <= 0:
            raise ValueError("invalid relay rate/idle limits")


@dataclass(frozen=True, slots=True)
class _Grant:
    session_id: str
    device_id: str
    edge_id: str
    capabilities: frozenset[str]
    expires_at: datetime
    token_digest: str
    lease_id: str
    fencing_token: int


class EdgeHubDebugTransport:
    """Encode relay commands on the existing outbound Edge protocol."""

    def __init__(self, hub: EdgeHub) -> None:
        self._hub = hub

    async def send_command(
        self,
        *,
        session_id: str,
        device_id: str,
        edge_id: str,
        capability: str,
        payload: Mapping[str, object],
        lease_id: str,
        fencing_token: int,
    ) -> str:
        command_id = f"debug/{session_id}/{secrets.token_urlsafe(12)}"
        kind = {
            "input.tap": "tap",
            "input.swipe": "swipe",
            "input.text": "text",
            "view.frame": "frame",
            "view.layout": "layout",
            "evidence.capture": "evidence.request",
            "debug.steps": "steps",
            "debug.variables": "variables",
        }.get(capability)
        if kind is None:
            raise SessionError("debug capability has no relay mapping")
        await self._hub.queue(
            edge_id,
            pb.CloudToEdge(
                relay_frame=pb.DebugRelayFrame(
                    session_id=session_id,
                    device_id=device_id,
                    request_id=command_id,
                    kind=kind,
                    capability=capability,
                    payload=json.dumps(
                        dict(payload), separators=(",", ":"), ensure_ascii=False
                    ).encode(),
                )
            ),
        )
        return command_id


class DebugRelay:
    """Serve one authenticated debug WebSocket at ``/debug``."""

    def __init__(
        self,
        store: DebugDeliveryStore,
        transport: RelayTransport,
        *,
        config: DebugRelayConfig,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._store = store
        self._transport = transport
        self._config = config
        self._now = now or (lambda: datetime.now(UTC))
        self._connections = asyncio.Semaphore(config.max_connections)
        self._sessions: dict[str, set[WebSocketLike]] = {}
        self._command_sessions: dict[str, str] = {}
        self._outbound_bytes: dict[WebSocketLike, int] = {}
        self._lock = asyncio.Lock()

    def attach_hub(self, hub: EdgeHub) -> None:
        """Route only known Edge acknowledgements/events to this relay."""
        hub.on_edge_message(self._accept_edge_message)

    async def _accept_edge_message(self, edge_id: str, message: pb.EdgeToCloud) -> None:
        body = message.WhichOneof("body")
        if body == "relay_frame":
            frame = message.relay_frame
            try:
                payload: object = json.loads(frame.payload.decode("utf-8"))
            except (UnicodeDecodeError, ValueError):
                return
            if not isinstance(payload, dict):
                return
            wire_type = {
                "view.frame": "frame",
                "view.layout": "layout",
                "evidence.capture": "evidence",
                "debug.ack": "debug.ack",
            }.get(frame.capability)
            if wire_type is None:
                return
            await self.publish_edge_event(
                frame.request_id,
                {**payload, "type": wire_type, "commandId": frame.request_id},
            )
            return
        if body == "command_ack":
            ack = message.command_ack
            await self.publish_edge_event(
                ack.command_id,
                {
                    "type": "debug.ack",
                    "commandId": ack.command_id,
                    "state": ack.state,
                    "errorCode": ack.error_code,
                    "detail": ack.detail,
                },
            )
            return
        if body == "evidence_ready":
            evidence = message.evidence_ready
            await self.publish_edge_event(
                evidence.command_id,
                {
                    "type": "evidence",
                    "commandId": evidence.command_id,
                    "evidenceId": evidence.evidence_id,
                    "kind": evidence.kind,
                    "sha256": evidence.sha256,
                    "size": evidence.size,
                },
            )

    async def handle_connection(self, websocket: WebSocketLike, path: str | None = None) -> None:
        """Handle a websocket; suitable as a websockets ``serve`` callback."""
        if path is None:
            path = getattr(getattr(websocket, "request", None), "path", "/debug")
        if path != "/debug":
            await self._close(websocket, _CLOSE_POLICY, "debug endpoint required")
            return
        if not self._origin_allowed(websocket):
            await self._close(websocket, _CLOSE_FORBIDDEN, "origin not allowed")
            return
        if not await self._try_acquire():
            await self._close(websocket, _CLOSE_POLICY, "connection limit reached")
            return
        session_id: str | None = None
        try:
            first = await self._recv_json(websocket, auth=True)
            grant = await self._authenticate(first)
            session_id = grant.session_id
            async with self._lock:
                self._sessions.setdefault(session_id, set()).add(websocket)
            await self._send_json(websocket, {"type": "ready", "sessionId": session_id})
            await self._run_messages(websocket, grant)
        except DebugRelayError as exc:
            await self._close(websocket, _CLOSE_UNAUTHENTICATED, str(exc))
        except TimeoutError:
            await self._close(websocket, _CLOSE_POLICY, "idle timeout")
        except ConnectionClosedOK:
            pass
        finally:
            async with self._lock:
                self._outbound_bytes.pop(websocket, None)
            if session_id is not None:
                async with self._lock:
                    peers = self._sessions.get(session_id)
                    if peers is not None:
                        peers.discard(websocket)
                        if not peers:
                            self._sessions.pop(session_id, None)
            self._connections.release()

    async def publish_edge_event(self, command_id: str, event: Mapping[str, object]) -> None:
        """Publish an allowlisted Edge event to the browser session."""
        session_id = self._command_sessions.get(command_id)
        if session_id is None:
            return
        event_type = event.get("type")
        if not isinstance(event_type, str) or event_type not in ALLOWED_EDGE_EVENT_TYPES:
            return
        encoded = json.dumps(dict(event), separators=(",", ":"), ensure_ascii=False)
        if len(encoded.encode()) > self._config.max_message_bytes:
            return
        async with self._lock:
            peers = tuple(self._sessions.get(session_id, ()))
        for peer in peers:
            await self._send_text(peer, encoded)

    async def _run_messages(self, websocket: WebSocketLike, grant: _Grant) -> None:
        window_start = time.monotonic()
        count = 0
        inbound = 0
        while True:
            raw = await asyncio.wait_for(websocket.recv(), self._config.idle_timeout_seconds)
            size = len(raw.encode() if isinstance(raw, str) else raw)
            if size > self._config.max_message_bytes:
                await self._close(websocket, _CLOSE_TOO_LARGE, "message too large")
                return
            inbound += size
            if inbound > self._config.max_inbound_bytes:
                await self._close(websocket, _CLOSE_POLICY, "inbound budget exceeded")
                return
            now = time.monotonic()
            if now - window_start >= 1:
                window_start, count = now, 0
            count += 1
            if count > self._config.max_messages_per_second:
                await self._close(websocket, _CLOSE_POLICY, "rate limit exceeded")
                return
            message = self._parse_message(raw)
            if grant.expires_at <= self._now():
                raise DebugRelayError("debug session is expired or revoked")
            message_type = message.get("type")
            if not isinstance(message_type, str) or message_type not in ALLOWED_MESSAGE_TYPES:
                raise DebugRelayError("message type is not allowed")
            if message.get("sessionId", grant.session_id) != grant.session_id:
                raise DebugRelayError("session does not match grant")
            if message_type not in grant.capabilities:
                raise DebugRelayError("capability is not granted")
            payload = {
                key: value for key, value in message.items() if key not in {"type", "sessionId"}
            }
            command_id = await self._transport.send_command(
                session_id=grant.session_id,
                device_id=grant.device_id,
                edge_id=grant.edge_id,
                capability=message_type,
                payload=payload,
                lease_id=grant.lease_id,
                fencing_token=grant.fencing_token,
            )
            self._command_sessions[command_id] = grant.session_id
            await self._send_json(websocket, {"type": "debug.accepted", "commandId": command_id})

    async def _authenticate(self, message: Mapping[str, object]) -> _Grant:
        if message.get("type") != AUTH_TYPE:
            raise DebugRelayError("first message must be debug.auth")
        session_id, token = message.get("sessionId"), message.get("token")
        if not isinstance(session_id, str) or not session_id or not isinstance(token, str):
            raise DebugRelayError("sessionId and token are required")
        record = await self._store.get(session_id)
        if record is None or record.relay_token_digest is None:
            raise DebugRelayError("invalid debug session")
        token_digest = hashlib.sha256(token.encode()).hexdigest()
        if not secrets.compare_digest(record.relay_token_digest, token_digest):
            raise DebugRelayError("invalid debug session")
        if record.state in {"REVOKED", "EXPIRED", "FAILED"} or record.expires_at <= self._now():
            raise DebugRelayError("debug session is expired or revoked")
        return _Grant(
            session_id=record.session_id,
            device_id=record.device_id,
            edge_id=record.edge_id,
            capabilities=frozenset(record.capabilities),
            expires_at=record.expires_at,
            token_digest=record.relay_token_digest,
            lease_id=record.lease_id or "",
            fencing_token=record.fencing_token or 0,
        )

    def _origin_allowed(self, websocket: WebSocketLike) -> bool:
        request = getattr(websocket, "request", None)
        headers = getattr(request, "headers", {})
        origin = headers.get("Origin") or headers.get("origin")
        return isinstance(origin, str) and origin in self._config.origins

    async def _recv_json(
        self, websocket: WebSocketLike, *, auth: bool = False
    ) -> dict[str, object]:
        raw = await asyncio.wait_for(websocket.recv(), self._config.idle_timeout_seconds)
        size = len(raw.encode() if isinstance(raw, str) else raw)
        if size > self._config.max_message_bytes:
            raise DebugRelayError("message too large")
        message = self._parse_message(raw)
        if auth and message.get("type") != AUTH_TYPE:
            raise DebugRelayError("first message must be debug.auth")
        return message

    @staticmethod
    def _parse_message(raw: str | bytes) -> dict[str, object]:
        if isinstance(raw, bytes):
            raise DebugRelayError("binary messages are not supported")
        try:
            decoded = json.loads(raw)
        except (TypeError, ValueError) as exc:
            raise DebugRelayError("message must be JSON") from exc
        if not isinstance(decoded, dict):
            raise DebugRelayError("message must be a JSON object")
        return decoded

    async def _try_acquire(self) -> bool:
        if self._connections.locked():
            return False
        await self._connections.acquire()
        return True

    async def _send_json(self, websocket: WebSocketLike, value: Mapping[str, object]) -> None:
        encoded = json.dumps(dict(value), separators=(",", ":"), ensure_ascii=False)
        await self._send_text(websocket, encoded)

    async def _send_text(self, websocket: WebSocketLike, encoded: str) -> None:
        size = len(encoded.encode())
        if size > self._config.max_message_bytes:
            raise DebugRelayError("outbound message too large")
        async with self._lock:
            total = self._outbound_bytes.get(websocket, 0) + size
            if total > self._config.max_outbound_bytes:
                raise DebugRelayError("outbound budget exceeded")
            self._outbound_bytes[websocket] = total
        if size > self._config.max_outbound_bytes:
            raise DebugRelayError("outbound budget exceeded")
        result = websocket.send(encoded)
        if result is not None:
            await result

    @staticmethod
    async def _close(websocket: WebSocketLike, code: int, reason: str) -> None:
        result = websocket.close(code=code, reason=reason)
        if result is not None:
            await result


def create_debug_server(
    relay: DebugRelay,
    *,
    bind: str,
    server_certificate: str | Path,
    server_private_key: str | Path,
) -> Any:
    """Create a TLS WebSocket server; callers own its lifecycle.

    ``websockets`` accepts an SSL context and performs the HTTP upgrade.  The
    relay still checks Origin and the path so this helper cannot accidentally
    become a generic WebSocket proxy.
    """
    host, separator, raw_port = bind.rpartition(":")
    if not separator or not host or not raw_port.isdecimal():
        raise DebugRelayError("debug bind must be HOST:PORT")
    port = int(raw_port)
    if not 1 <= port <= 65535 or port == 65000:
        raise DebugRelayError("invalid debug bind port")
    return create_debug_server_from_files(
        relay,
        bind=bind,
        certificate_path=str(server_certificate),
        private_key_path=str(server_private_key),
    )


def create_debug_server_from_files(
    relay: DebugRelay,
    *,
    bind: str,
    certificate_path: str,
    private_key_path: str,
) -> Any:
    """Create a TLS server from paths without exposing a plaintext fallback."""
    import websockets.asyncio.server

    host, separator, raw_port = bind.rpartition(":")
    if not separator or not host or not raw_port.isdecimal():
        raise DebugRelayError("debug bind must be HOST:PORT")
    port = int(raw_port)
    if not 1 <= port <= 65535 or port == 65000:
        raise DebugRelayError("invalid debug bind port")
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(certificate_path, private_key_path)
    from websockets.asyncio.server import ServerConnection

    async def adapter(websocket: ServerConnection) -> None:
        await relay.handle_connection(websocket)  # type: ignore[arg-type]

    return websockets.asyncio.server.serve(
        adapter,
        host,
        port,
        ssl=context,
        origins=[origin for origin in relay._config.origins],  # type: ignore[misc]
        max_size=relay._config.max_message_bytes,
        compression=None,
    )
