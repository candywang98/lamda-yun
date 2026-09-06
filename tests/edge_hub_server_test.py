from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import grpc
import pytest

ROOT = Path(__file__).parents[1]
for source in ("packages/edge-protocol/src", "services/edge-hub/src"):
    sys.path.insert(0, str(ROOT / source))

import cloudctl_edge_hub.main as edge_hub_main
import cloudctl_edge_hub.server as edge_hub_server
from cloudctl_edge_hub.main import (
    DEFAULT_BIND,
    RuntimeConfig,
    parse_config,
    read_required_file,
    run_server,
)
from cloudctl_edge_hub.server import ServerConfigurationError, create_server, validate_bind


def test_runtime_defaults_to_public_relay_port_and_requires_explicit_tls_paths(
    tmp_path: Path,
) -> None:
    paths = [tmp_path / name for name in ("server.crt", "server.key", "client-ca.crt")]
    config = parse_config(
        [
            "--server-certificate",
            str(paths[0]),
            "--server-private-key",
            str(paths[1]),
            "--client-ca-certificate",
            str(paths[2]),
        ]
    )
    assert config.bind == DEFAULT_BIND == "0.0.0.0:7443"
    assert config.server_certificate_path == paths[0]
    assert config.server_private_key_path == paths[1]
    assert config.client_ca_certificate_path == paths[2]


@pytest.mark.parametrize("bind", ["0.0.0.0:65000", "127.0.0.1:65000", "[::]:65000"])
def test_device_local_port_is_rejected_for_every_host(bind: str) -> None:
    with pytest.raises(ServerConfigurationError, match="device service port"):
        validate_bind(bind)


@pytest.mark.parametrize("bind", ["", "7443", "0.0.0.0:", "0.0.0.0:0", "host:65536"])
def test_invalid_bind_is_rejected(bind: str) -> None:
    with pytest.raises(ServerConfigurationError):
        validate_bind(bind)


def test_empty_or_missing_tls_files_are_rejected(tmp_path: Path) -> None:
    empty = tmp_path / "empty.pem"
    empty.write_text("  \n", encoding="utf-8")
    with pytest.raises(ServerConfigurationError, match="file is empty"):
        read_required_file(empty, "server certificate")
    with pytest.raises(ServerConfigurationError, match="cannot read"):
        read_required_file(tmp_path / "missing.pem", "client CA certificate")


def test_nonempty_tls_file_is_loaded_without_mutation(tmp_path: Path) -> None:
    certificate = tmp_path / "server.crt"
    expected = b"-----BEGIN CERTIFICATE-----\nfixture\n-----END CERTIFICATE-----\n"
    certificate.write_bytes(expected)
    assert read_required_file(certificate, "server certificate") == expected


def test_grpc_server_credentials_always_require_client_authentication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class FakeGrpcServer:
        def add_secure_port(self, bind: str, credentials: object) -> int:
            captured["bind"] = bind
            captured["credentials"] = credentials
            return 7443

    fake_server = FakeGrpcServer()

    def fake_server_factory(*, options: object) -> FakeGrpcServer:
        captured["options"] = options
        return fake_server

    def fake_credentials(
        pairs: object, *, root_certificates: bytes, require_client_auth: bool
    ) -> object:
        captured["pairs"] = pairs
        captured["root_certificates"] = root_certificates
        captured["require_client_auth"] = require_client_auth
        return object()

    monkeypatch.setattr(grpc.aio, "server", fake_server_factory)
    monkeypatch.setattr(grpc, "ssl_server_credentials", fake_credentials)
    monkeypatch.setattr(
        edge_hub_server.pb_grpc, "add_EdgeControlServicer_to_server", lambda *_: None
    )

    result = create_server(
        object(),  # type: ignore[arg-type]
        bind=DEFAULT_BIND,
        server_certificate=b"server-certificate",
        server_private_key=b"server-private-key",
        client_ca_certificate=b"client-ca-certificate",
    )

    assert result is fake_server
    assert captured["bind"] == DEFAULT_BIND
    assert captured["root_certificates"] == b"client-ca-certificate"
    assert captured["require_client_auth"] is True
    assert captured["pairs"] == [(b"server-private-key", b"server-certificate")]


@pytest.mark.asyncio
async def test_runtime_starts_then_gracefully_stops_on_shutdown_event(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = [tmp_path / name for name in ("server.crt", "server.key", "client-ca.crt")]
    contents = (b"certificate", b"private-key", b"client-ca")
    for path, content in zip(paths, contents, strict=True):
        path.write_bytes(content)

    class FakeServer:
        def __init__(self) -> None:
            self.started = False
            self.stop_grace: float | None = None

        async def start(self) -> None:
            self.started = True

        async def stop(self, grace: float) -> None:
            self.stop_grace = grace

    fake_server = FakeServer()
    captured: dict[str, Any] = {}

    def fake_create_server(service: object, **kwargs: Any) -> FakeServer:
        captured.update(kwargs)
        return fake_server

    monkeypatch.setattr(edge_hub_main, "create_server", fake_create_server)
    shutdown = edge_hub_main.asyncio.Event()
    shutdown.set()
    config = RuntimeConfig(
        bind=DEFAULT_BIND,
        server_certificate_path=paths[0],
        server_private_key_path=paths[1],
        client_ca_certificate_path=paths[2],
        graceful_stop_seconds=7.0,
        hub_state_db_path=tmp_path / "hub-state.db",
    )

    await run_server(config, shutdown)

    assert fake_server.started is True
    assert fake_server.stop_grace == 7.0
    assert captured["bind"] == DEFAULT_BIND
    assert captured["server_certificate"] == contents[0]
    assert captured["server_private_key"] == contents[1]
    assert captured["client_ca_certificate"] == contents[2]
