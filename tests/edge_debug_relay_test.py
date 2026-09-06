from __future__ import annotations

import asyncio
import hashlib
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for source in ("packages/edge-protocol/src", "services/edge-hub/src"):
    sys.path.insert(0, str(ROOT / source))

from cloudctl_edge_hub.debug_delivery import DebugDeliveryRecord, InMemoryDebugDeliveryStore
from cloudctl_edge_hub.debug_relay import DebugRelay, DebugRelayConfig
from cloudctl_edge_protocol import edge_control_pb2 as pb


class _Request:
    path = "/debug"
    headers = {"Origin": "https://studio.example"}


class _Socket:
    request = _Request()

    def __init__(self, messages: list[str]) -> None:
        self.messages = iter(messages)
        self.sent: list[str] = []
        self.closed: tuple[int, str] | None = None

    async def recv(self) -> str:
        try:
            return next(self.messages)
        except StopIteration:
            await asyncio.sleep(0)
            raise TimeoutError from None

    async def send(self, value: str) -> None:
        self.sent.append(value)

    async def close(self, code: int = 1000, reason: str = "") -> None:
        self.closed = (code, reason)


class _Transport:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def send_command(self, **kwargs: object) -> str:
        self.calls.append(kwargs)
        return "cmd-1"


def _record(token: str, *, state: str = "QUEUED") -> DebugDeliveryRecord:
    return DebugDeliveryRecord(
        session_id="s1",
        edge_id="e1",
        device_id="phone-1",
        capabilities=("input.tap", "view.frame"),
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
        state=state,
        lease_id="lease-1",
        fencing_token=3,
        relay_token_digest=hashlib.sha256(token.encode()).hexdigest(),
    )


@pytest.mark.asyncio
async def test_auth_and_explicit_command_forwarding() -> None:
    token = "a" * 40
    store = InMemoryDebugDeliveryStore()
    await store.create(_record(token))
    transport = _Transport()
    relay = DebugRelay(
        store,
        transport,
        config=DebugRelayConfig(origins=("https://studio.example",)),
    )
    socket = _Socket(
        [
            json.dumps({"type": "debug.auth", "sessionId": "s1", "token": token}),
            json.dumps({"type": "input.tap", "x": 10, "y": 20}),
        ]
    )
    await relay.handle_connection(socket)
    assert transport.calls[0]["device_id"] == "phone-1"
    assert transport.calls[0]["lease_id"] == "lease-1"
    assert transport.calls[0]["fencing_token"] == 3
    assert json.loads(socket.sent[0])["type"] == "ready"


@pytest.mark.asyncio
async def test_origin_and_capability_are_enforced() -> None:
    token = "b" * 40
    store = InMemoryDebugDeliveryStore()
    await store.create(_record(token))
    relay = DebugRelay(
        store,
        _Transport(),
        config=DebugRelayConfig(origins=("https://studio.example",)),
    )
    socket = _Socket(
        [
            json.dumps({"type": "debug.auth", "sessionId": "s1", "token": token}),
            json.dumps({"type": "input.text", "text": "blocked"}),
        ]
    )
    socket.request.headers = {"Origin": "https://evil.example"}
    await relay.handle_connection(socket)
    assert socket.closed is not None and socket.closed[0] == 4403


@pytest.mark.asyncio
async def test_edge_frame_layout_evidence_and_ack_are_published() -> None:
    relay = DebugRelay(
        InMemoryDebugDeliveryStore(),
        _Transport(),
        config=DebugRelayConfig(origins=("https://studio.example",)),
    )
    socket = _Socket([])
    relay._sessions["s1"] = {socket}

    frames = (
        ("cmd-frame", "view.frame", {"image": "sha256:abc"}, "frame"),
        ("cmd-layout", "view.layout", {"nodes": []}, "layout"),
        ("cmd-evidence", "evidence.capture", {"evidenceId": "ev-1"}, "evidence"),
    )
    for command_id, capability, payload, _ in frames:
        relay._command_sessions[command_id] = "s1"
        await relay._accept_edge_message(
            "e1",
            pb.EdgeToCloud(
                relay_frame=pb.DebugRelayFrame(
                    session_id="s1",
                    device_id="phone-1",
                    request_id=command_id,
                    kind="frame",
                    capability=capability,
                    payload=json.dumps(payload).encode(),
                )
            ),
        )

    relay._command_sessions["cmd-ack"] = "s1"
    await relay._accept_edge_message(
        "e1",
        pb.EdgeToCloud(command_ack=pb.CommandAck(command_id="cmd-ack", state="ACCEPTED")),
    )

    published = [json.loads(item) for item in socket.sent]
    assert [item["type"] for item in published] == [
        "frame",
        "layout",
        "evidence",
        "debug.ack",
    ]
    assert [item["commandId"] for item in published] == [
        "cmd-frame",
        "cmd-layout",
        "cmd-evidence",
        "cmd-ack",
    ]
