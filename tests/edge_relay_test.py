from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from cloudctl_edge_hub.relay import RelayRouter, relay_grant_from_token
from cloudctl_edge_hub.session import EdgeHub, InMemoryHubStore, SessionError
from cloudctl_edge_protocol import edge_control_pb2 as pb


@pytest.mark.asyncio
async def test_outbound_relay_binds_browser_to_edge_and_routes_both_directions() -> None:
    hub = EdgeHub(InMemoryHubStore())
    router = RelayRouter(hub)
    await router.register(
        relay_grant_from_token(
            session_id="s1",
            edge_id="edge-a",
            device_id="device-a",
            capabilities=["input.tap", "view.frame"],
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
            token="x" * 48,
        )
    )
    browser = await router.authenticate(session_id="s1", token="x" * 48)
    await browser.send(
        request_id="r1", kind="tap", capability="input.tap", payload={"x": 4, "y": 9}
    )
    stream = hub.open("edge-a", 0)
    await anext(stream)
    outbound = await anext(stream)
    assert outbound.relay_frame.device_id == "device-a"
    assert outbound.relay_frame.session_id == "s1"
    assert b'"x":4' in outbound.relay_frame.payload
    await stream.aclose()

    await hub.accept(
        "edge-a",
        pb.EdgeToCloud(
            sequence=1,
            relay_frame=pb.DebugRelayFrame(
                session_id="s1",
                device_id="device-a",
                request_id="r1",
                kind="frame",
                capability="view.frame",
                payload=b"frame-data",
            ),
        ),
    )
    response = await browser.receive()
    assert response.payload == b"frame-data"


@pytest.mark.asyncio
async def test_relay_revocation_and_capability_gates_are_immediate() -> None:
    hub = EdgeHub(InMemoryHubStore())
    router = RelayRouter(hub)
    await router.register(
        relay_grant_from_token(
            session_id="s2",
            edge_id="edge-a",
            device_id="device-a",
            capabilities=["input.tap"],
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
            token="y" * 48,
        )
    )
    browser = await router.authenticate(session_id="s2", token="y" * 48)
    with pytest.raises(SessionError, match="not granted"):
        await browser.send(
            request_id="r2", kind="evidence.request", capability="evidence.capture", payload={}
        )
    await router.revoke("s2")
    with pytest.raises(SessionError, match="closed"):
        await browser.send(request_id="r3", kind="tap", capability="input.tap", payload={})
