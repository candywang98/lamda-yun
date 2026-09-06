"""Outbox sink for durable debug-session delivery.

The sink deliberately depends only on a small handler protocol.  Deployments
can provide a handler backed by an mTLS Edge Hub client; tests can provide the
in-process ``DebugGrantDelivery``.  Bearer tokens are passed only to the
handler and are never logged or copied into sink state.
"""

from __future__ import annotations

from typing import Any, Protocol

from .sinks import EventEnvelope


class DebugEventHandler(Protocol):
    async def queue_from_event(self, payload: dict[str, object]) -> Any: ...

    async def revoke_from_event(self, payload: dict[str, object]) -> Any: ...


class DebugRelayEventSink:
    """Route only debug grant/revoke events with event-id deduplication."""

    _GRANT = "debug.session.grant_requested"
    _REVOKE = "debug.session.revoked"

    def __init__(self, handler: DebugEventHandler) -> None:
        self._handler = handler
        self._seen: set[str] = set()

    async def publish(self, event: EventEnvelope) -> None:
        if event.event_type not in {self._GRANT, self._REVOKE}:
            return
        if event.id in self._seen:
            return
        payload = dict(event.payload)
        # Do not allow routing metadata to override the signed aggregate.
        payload.setdefault("sessionId", event.aggregate_id)
        if event.event_type == self._GRANT:
            await self._handler.queue_from_event(payload)
        else:
            await self._handler.revoke_from_event(payload)
        self._seen.add(event.id)
