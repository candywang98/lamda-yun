from __future__ import annotations

import hashlib
import json
import socket
import ssl
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import websockets.asyncio.client
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

ROOT = Path(__file__).resolve().parents[1]
for source in ("packages/edge-protocol/src", "services/edge-hub/src"):
    sys.path.insert(0, str(ROOT / source))

from cloudctl_edge_hub.debug_delivery import DebugDeliveryRecord, InMemoryDebugDeliveryStore
from cloudctl_edge_hub.debug_relay import DebugRelay, DebugRelayConfig, create_debug_server


class Transport:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def send_command(self, **kwargs: object) -> str:
        self.calls.append(kwargs)
        return "command-1"


def _certificate(tmp_path: Path) -> tuple[Path, Path]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(UTC) - timedelta(minutes=1))
        .not_valid_after(datetime.now(UTC) + timedelta(minutes=5))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")]), critical=False)
        .sign(key, hashes.SHA256())
    )
    cert_path, key_path = tmp_path / "server.crt", tmp_path / "server.key"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )
    return cert_path, key_path


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.mark.asyncio
async def test_real_tls_wss_auth_and_command_forwarding(tmp_path: Path) -> None:
    token = "t" * 48
    store = InMemoryDebugDeliveryStore()
    await store.create(
        DebugDeliveryRecord(
            session_id="s1",
            edge_id="e1",
            device_id="phone-1",
            capabilities=("input.tap",),
            expires_at=datetime.now(UTC) + timedelta(minutes=2),
            state="QUEUED",
            lease_id="lease-1",
            fencing_token=7,
            relay_token_digest=hashlib.sha256(token.encode()).hexdigest(),
        )
    )
    transport = Transport()
    relay = DebugRelay(
        store, transport, config=DebugRelayConfig(origins=("https://studio.example",))
    )
    cert_path, key_path = _certificate(tmp_path)
    server = await create_debug_server(
        relay,
        bind=f"127.0.0.1:{_free_port()}",
        server_certificate=cert_path,
        server_private_key=key_path,
    )
    port = server.sockets[0].getsockname()[1]
    client_context = ssl.create_default_context(cafile=str(cert_path))
    try:
        async with websockets.asyncio.client.connect(
            f"wss://localhost:{port}/debug",
            ssl=client_context,
            origin="https://studio.example",
            proxy=None,
        ) as websocket:
            await websocket.send(
                json.dumps({"type": "debug.auth", "sessionId": "s1", "token": token})
            )
            assert json.loads(await websocket.recv())["type"] == "ready"
            await websocket.send(json.dumps({"type": "input.tap", "x": 10, "y": 20}))
            assert json.loads(await websocket.recv())["type"] == "debug.accepted"
    finally:
        server.close()
        await server.wait_closed()
    assert transport.calls[0]["lease_id"] == "lease-1"
    assert transport.calls[0]["fencing_token"] == 7
