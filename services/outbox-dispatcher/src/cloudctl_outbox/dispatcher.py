"""At-least-once dispatcher with explicit claim ownership."""

from __future__ import annotations

import asyncio
import logging
import uuid

from cloudctl_observability import bind_context

from .sinks import EventEnvelope, EventSink
from .store import OutboxStore


class OutboxDispatcher:
    def __init__(
        self,
        store: OutboxStore,
        sink: EventSink,
        *,
        owner: str | None = None,
        poll_seconds: float = 1.0,
        batch_size: int = 100,
    ) -> None:
        self.store = store
        self.sink = sink
        self.owner = owner or f"dispatcher-{uuid.uuid4()}"
        self.poll_seconds = poll_seconds
        self.batch_size = batch_size
        self.logger = logging.getLogger("cloudctl.outbox.dispatcher")

    async def dispatch_once(self) -> int:
        rows = await self.store.claim(self.owner, batch_size=self.batch_size)
        delivered = 0
        for row in rows:
            event = EventEnvelope(
                id=row.id,
                tenant_id=row.tenant_id,
                aggregate_type=row.aggregate_type,
                aggregate_id=row.aggregate_id,
                event_type=row.event_type,
                payload=row.payload,
                occurred_at=row.occurred_at,
            )
            with bind_context(tenant_id=event.tenant_id):
                try:
                    await self.sink.publish(event)
                except Exception as exc:
                    await self.store.mark_failed(event.id, self.owner, type(exc).__name__)
                    self.logger.exception(
                        "outbox event delivery failed",
                        extra={"fields": {"event_id": event.id, "event_type": event.event_type}},
                    )
                else:
                    if await self.store.mark_published(event.id, self.owner):
                        delivered += 1
        return delivered

    async def run(self, stop: asyncio.Event | None = None) -> None:
        stop_event = stop or asyncio.Event()
        while not stop_event.is_set():
            delivered = await self.dispatch_once()
            if delivered == 0:
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=self.poll_seconds)
                except TimeoutError:
                    pass
