from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from cloudctl_edge_hub.debug_delivery import DebugGrantDelivery, InMemoryDebugDeliveryStore
from cloudctl_edge_hub.session import EdgeHub, InMemoryHubStore
from cloudctl_edge_protocol import edge_control_pb2 as pb


@pytest.mark.asyncio
async def test_debug_grant_is_queued_replayed_and_acknowledged() -> None:
    hub_store = InMemoryHubStore()
    hub = EdgeHub(hub_store)
    delivery_store = InMemoryDebugDeliveryStore()
    delivery = DebugGrantDelivery(hub, delivery_store)
    expires = datetime.now(UTC) + timedelta(minutes=10)

    queued = await delivery.queue(
        session_id="session-1",
        edge_id="edge-a",
        device_id="device-a",
        capabilities=["view.frame", "view.layout"],
        expires_at=expires,
    )
    assert queued.state == "QUEUED"
    stream = hub.open("edge-a", 0)
    await anext(stream)
    grant = await anext(stream)
    await stream.aclose()
    assert grant.debug_grant.session_id == "session-1"
    assert list(grant.debug_grant.capabilities) == ["view.frame", "view.layout"]

    inserted = await hub.accept(
        "edge-a",
        pb.EdgeToCloud(
            sequence=1,
            command_ack=pb.CommandAck(command_id="session-1", state="ACCEPTED"),
        ),
    )
    assert inserted is True
    accepted = await delivery_store.get("session-1")
    assert accepted is not None
    assert accepted.state == "ACCEPTED"


@pytest.mark.asyncio
async def test_debug_grant_can_be_created_from_control_plane_event() -> None:
    hub = EdgeHub(InMemoryHubStore())
    store = InMemoryDebugDeliveryStore()
    delivery = DebugGrantDelivery(hub, store)
    record = await delivery.queue_from_event(
        {
            "sessionId": "session-event",
            "edgeId": "edge-event",
            "deviceId": "device-event",
            "capabilities": ["view.frame"],
            "expiresAt": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
            "fencingToken": 1.0,
        }
    )
    assert record.edge_id == "edge-event"
    assert record.state == "QUEUED"
    assert record.fencing_token == 1
