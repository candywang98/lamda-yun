from datetime import UTC, datetime

import pytest
from cloudctl_outbox.debug_stream_sink import DebugStreamSink
from cloudctl_outbox.sinks import EventEnvelope


class Publisher:
    def __init__(self) -> None:
        self.events: list[EventEnvelope] = []

    async def publish_debug_event(self, event: EventEnvelope) -> None:
        self.events.append(event)


@pytest.mark.asyncio
async def test_stream_sink_is_idempotent_and_ignores_unrelated_events() -> None:
    publisher = Publisher()
    sink = DebugStreamSink(publisher)
    event = EventEnvelope(
        "evt-1",
        "tenant-1",
        "debug_session",
        "session-1",
        "debug.session.grant_requested",
        {"sessionId": "session-1"},
        datetime.now(UTC),
    )
    await sink.publish(event)
    await sink.publish(event)
    await sink.publish(
        EventEnvelope("evt-2", "tenant-1", "other", "x", "other.event", {}, datetime.now(UTC))
    )
    assert publisher.events == [event]
