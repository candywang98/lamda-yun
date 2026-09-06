"""Debug grant delivery and acknowledgement tracking over the Edge stream."""

from __future__ import annotations

import asyncio
import hashlib
import secrets
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Protocol

from cloudctl_edge_protocol import edge_control_pb2 as pb
from google.protobuf.timestamp_pb2 import Timestamp

from .relay import RelayRouter, relay_grant_from_token
from .session import EdgeHub, SessionError

ACK_STATES = frozenset({"RECEIVED", "ACCEPTED", "REJECTED", "FAILED"})
ALLOWED_DEBUG_CAPABILITIES = frozenset(
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


@dataclass(frozen=True, slots=True)
class DebugDeliveryRecord:
    session_id: str
    edge_id: str
    device_id: str
    capabilities: tuple[str, ...]
    expires_at: datetime
    state: str
    error_code: str | None = None
    detail: str | None = None
    cloud_sequence: int | None = None
    lease_id: str | None = None
    fencing_token: int | None = None
    # Only a digest is retained in the delivery store; the bearer itself is never logged.
    relay_token_digest: str | None = None


class DebugDeliveryStore(Protocol):
    async def create(self, record: DebugDeliveryRecord) -> None: ...
    async def update(
        self,
        session_id: str,
        *,
        state: str,
        error_code: str | None = None,
        detail: str | None = None,
        cloud_sequence: int | None = None,
    ) -> DebugDeliveryRecord: ...
    async def get(self, session_id: str) -> DebugDeliveryRecord | None: ...


class InMemoryDebugDeliveryStore:
    def __init__(self) -> None:
        self._records: dict[str, DebugDeliveryRecord] = {}
        self._lock = asyncio.Lock()

    async def create(self, record: DebugDeliveryRecord) -> None:
        async with self._lock:
            existing = self._records.get(record.session_id)
            if existing is not None and existing != record:
                raise SessionError("debug session delivery already exists with different input")
            self._records[record.session_id] = record

    async def update(
        self,
        session_id: str,
        *,
        state: str,
        error_code: str | None = None,
        detail: str | None = None,
        cloud_sequence: int | None = None,
    ) -> DebugDeliveryRecord:
        async with self._lock:
            existing = self._records.get(session_id)
            if existing is None:
                raise SessionError(f"unknown debug session delivery {session_id}")
            updated = replace(
                existing,
                state=state,
                error_code=error_code,
                detail=detail,
                cloud_sequence=cloud_sequence or existing.cloud_sequence,
            )
            self._records[session_id] = updated
            return updated

    async def get(self, session_id: str) -> DebugDeliveryRecord | None:
        async with self._lock:
            return self._records.get(session_id)


class DebugGrantDelivery:
    """Converts a control-plane grant event to protobuf and consumes Edge ACKs."""

    def __init__(
        self, hub: EdgeHub, store: DebugDeliveryStore, relay_router: RelayRouter | None = None
    ) -> None:
        self._hub = hub
        self._store = store
        self._relay_router = relay_router
        hub.on_edge_message(self.accept_edge_message)

    async def queue(
        self,
        *,
        session_id: str,
        edge_id: str,
        device_id: str,
        capabilities: list[str],
        expires_at: datetime,
        relay_token: str | None = None,
        lease_id: str | None = None,
        fencing_token: int | None = None,
    ) -> DebugDeliveryRecord:
        if not all((session_id, edge_id, device_id)):
            raise SessionError("session_id, edge_id and device_id are required")
        if not capabilities:
            raise SessionError("debug grant capabilities are required")
        normalized_capabilities = set(capabilities)
        if not normalized_capabilities <= ALLOWED_DEBUG_CAPABILITIES:
            raise SessionError("debug grant contains a prohibited capability")
        token = relay_token or secrets.token_urlsafe(48)
        if len(token) < 32:
            raise SessionError("debug grant relay token is too short")
        aware_expiry = (
            expires_at if expires_at.tzinfo is not None else expires_at.replace(tzinfo=UTC)
        )
        if aware_expiry <= datetime.now(UTC):
            raise SessionError("debug grant already expired")
        record = DebugDeliveryRecord(
            session_id=session_id,
            edge_id=edge_id,
            device_id=device_id,
            capabilities=tuple(sorted(normalized_capabilities)),
            expires_at=aware_expiry,
            state="PENDING",
            lease_id=lease_id or f"debug-lease/{session_id}",
            fencing_token=fencing_token or 1,
            relay_token_digest=hashlib.sha256(token.encode("utf-8")).hexdigest(),
        )
        await self._store.create(record)
        if self._relay_router is not None:
            await self._relay_router.register(
                relay_grant_from_token(
                    session_id=session_id,
                    edge_id=edge_id,
                    device_id=device_id,
                    capabilities=list(record.capabilities),
                    expires_at=aware_expiry,
                    token=token,
                )
            )
        timestamp = Timestamp()
        timestamp.FromDatetime(aware_expiry)
        stored = await self._hub.queue(
            edge_id,
            pb.CloudToEdge(
                debug_grant=pb.DebugSessionGrant(
                    session_id=session_id,
                    device_id=device_id,
                    expires_at=timestamp,
                    capabilities=record.capabilities,
                    lease_id=record.lease_id or "",
                    fencing_token=record.fencing_token or 0,
                    relay_token=token,
                )
            ),
        )
        return await self._store.update(
            session_id,
            state="QUEUED",
            cloud_sequence=stored.sequence,
        )

    async def queue_from_event(self, payload: dict[str, object]) -> DebugDeliveryRecord:
        try:
            raw_capabilities = payload["capabilities"]
            if not isinstance(raw_capabilities, list) or not all(
                isinstance(item, str) for item in raw_capabilities
            ):
                raise TypeError("capabilities must be a string list")
            capabilities = list(raw_capabilities)
            return await self.queue(
                session_id=str(payload["sessionId"]),
                edge_id=str(payload["edgeId"]),
                device_id=str(payload["deviceId"]),
                capabilities=capabilities,
                expires_at=datetime.fromisoformat(str(payload["expiresAt"])),
                relay_token=(
                    str(payload["relayToken"]) if payload.get("relayToken") is not None else None
                ),
                lease_id=(str(payload["leaseId"]) if payload.get("leaseId") is not None else None),
                fencing_token=_optional_positive_int(payload.get("fencingToken")),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise SessionError("invalid debug grant event payload") from exc

    async def revoke_from_event(self, payload: dict[str, object]) -> pb.CloudToEdge:
        """Queue a revocation without ever carrying a bearer token in the event."""
        try:
            session_id = str(payload["sessionId"])
            device_id = str(payload["deviceId"])
            if not session_id or not device_id:
                raise ValueError("session and device are required")
            if self._relay_router is not None:
                await self._relay_router.revoke(session_id)
            queued = await self._hub.queue(
                str(payload["edgeId"]),
                pb.CloudToEdge(
                    debug_revoke=pb.DebugSessionRevoke(
                        session_id=session_id,
                        device_id=device_id,
                        reason=str(payload.get("reason", "revoked"))[:1000],
                    )
                ),
            )
            # Revocation is authoritative at the cloud ingress immediately;
            # the Edge message is still delivered for device-side cleanup.
            existing = await self._store.get(session_id)
            if existing is not None:
                await self._store.update(
                    session_id,
                    state="REVOKED",
                    error_code="REVOKED",
                    detail=str(payload.get("reason", "revoked"))[:1000],
                    cloud_sequence=queued.sequence,
                )
            return queued
        except (KeyError, TypeError, ValueError) as exc:
            raise SessionError("invalid debug revoke event payload") from exc

    async def accept_edge_message(self, edge_id: str, message: pb.EdgeToCloud) -> None:
        if message.WhichOneof("body") != "command_ack":
            return
        ack = message.command_ack
        record = await self._store.get(ack.command_id)
        if record is None:
            return
        if record.edge_id != edge_id:
            raise SessionError("debug grant ACK came from a different Edge")
        if ack.state not in ACK_STATES:
            raise SessionError(f"invalid debug grant ACK state {ack.state}")
        await self._store.update(
            record.session_id,
            state=ack.state,
            error_code=ack.error_code or None,
            detail=ack.detail or None,
        )


def _optional_positive_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("fencingToken must be a positive integer")
    return value
