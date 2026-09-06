from __future__ import annotations

from datetime import UTC, datetime

import pytest
from cloudctl_outbox.debug_sink import DebugRelayEventSink
from cloudctl_outbox.sinks import EventEnvelope


class Handler:
    def __init__(self) -> None:
        self.grants: list[dict[str, object]] = []
        self.revokes: list[dict[str, object]] = []

    async def queue_from_event(self, payload: dict[str, object]) -> None:
        self.grants.append(payload)

    async def revoke_from_event(self, payload: dict[str, object]) -> None:
        self.revokes.append(payload)


def event(event_id: str, event_type: str, payload: dict[str, object]) -> EventEnvelope:
    return EventEnvelope(
        event_id, "t1", "debug_session", "s1", event_type, payload, datetime.now(UTC)
    )


@pytest.mark.asyncio
async def test_debug_sink_routes_and_deduplicates_without_logging_token() -> None:
    handler = Handler()
    sink = DebugRelayEventSink(handler)
    grant = event("e1", "debug.session.grant_requested", {"relayToken": "secret"})
    await sink.publish(grant)
    await sink.publish(grant)
    await sink.publish(event("e2", "debug.session.revoked", {"deviceId": "d1", "edgeId": "e1"}))
    await sink.publish(event("e3", "other.event", {"relayToken": "ignored"}))
    assert len(handler.grants) == 1 and handler.grants[0]["sessionId"] == "s1"
    assert len(handler.revokes) == 1
