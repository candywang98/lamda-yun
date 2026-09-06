"""Idempotent outbox delivery sinks."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class EventEnvelope:
    id: str
    tenant_id: str
    aggregate_type: str
    aggregate_id: str
    event_type: str
    payload: dict[str, Any]
    occurred_at: datetime


class EventSink(Protocol):
    async def publish(self, event: EventEnvelope) -> None: ...


class InMemorySink:
    def __init__(self) -> None:
        self.events: list[EventEnvelope] = []
        self._seen: set[str] = set()

    async def publish(self, event: EventEnvelope) -> None:
        if event.id in self._seen:
            return
        self._seen.add(event.id)
        self.events.append(event)


class LoggingSink:
    def __init__(self, logger: logging.Logger | None = None) -> None:
        self.logger = logger or logging.getLogger("cloudctl.outbox")

    async def publish(self, event: EventEnvelope) -> None:
        self.logger.info(
            "outbox event delivered",
            extra={
                "fields": {
                    "event_id": event.id,
                    "tenant_id": event.tenant_id,
                    "event_type": event.event_type,
                    "aggregate_id": event.aggregate_id,
                }
            },
        )


class FanoutSink:
    def __init__(self, *sinks: EventSink) -> None:
        self.sinks = sinks

    async def publish(self, event: EventEnvelope) -> None:
        for sink in self.sinks:
            await sink.publish(event)
