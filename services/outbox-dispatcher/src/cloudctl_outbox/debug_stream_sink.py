"""Event sink adapter for a long-lived authenticated Edge Hub stream."""

from __future__ import annotations

from typing import Any, Protocol

from .sinks import EventEnvelope


class DebugStreamPublisher(Protocol):
    async def publish_debug_event(self, event: EventEnvelope) -> Any: ...


class DebugStreamSink:
    """Route debug events through an already-authenticated mTLS stream.

    The stream owner is responsible for reconnect/backoff. This sink provides
    event-id deduplication so dispatcher retries cannot duplicate grants.
    """

    _EVENTS = frozenset({"debug.session.grant_requested", "debug.session.revoked"})

    def __init__(self, publisher: DebugStreamPublisher) -> None:
        self._publisher = publisher
        self._seen: set[str] = set()

    async def publish(self, event: EventEnvelope) -> None:
        if event.event_type not in self._EVENTS or event.id in self._seen:
            return
        await self._publisher.publish_debug_event(event)
        self._seen.add(event.id)
