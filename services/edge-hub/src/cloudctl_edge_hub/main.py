"""Executable mTLS Edge Hub runtime."""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .debug_delivery import DebugDeliveryStore, DebugGrantDelivery
from .debug_relay import DebugRelay, DebugRelayConfig, EdgeHubDebugTransport, create_debug_server
from .grpc_service import EdgeControlService
from .identity import PeerIdentityVerifier
from .server import ServerConfigurationError, create_server, validate_bind
from .session import EdgeHub, HubStore, SessionError
from .sqlite_debug_store import SqliteDebugDeliveryStore
from .sqlite_hub_store import SqliteHubStore

LOGGER = logging.getLogger("cloudctl.edge_hub")
DEFAULT_BIND = "0.0.0.0:7443"
DEFAULT_HUB_STATE_DB = Path("/var/lib/cloudctl-edge-hub/hub-state.db")


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    bind: str
    server_certificate_path: Path
    server_private_key_path: Path
    client_ca_certificate_path: Path
    graceful_stop_seconds: float
    hub_state_db_path: Path = DEFAULT_HUB_STATE_DB
    debug_wss_enabled: bool = False
    debug_bind: str | None = None
    debug_origins: tuple[str, ...] = ()
    debug_server_certificate_path: Path | None = None
    debug_server_private_key_path: Path | None = None
    debug_delivery_db_path: Path | None = None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the CloudCtl Edge Hub with mandatory mutual TLS."
    )
    parser.add_argument("--bind", default=DEFAULT_BIND, help="gRPC bind address")
    parser.add_argument("--server-certificate", required=True, type=Path)
    parser.add_argument("--server-private-key", required=True, type=Path)
    parser.add_argument("--client-ca-certificate", required=True, type=Path)
    parser.add_argument("--graceful-stop-seconds", default=20.0, type=float)
    parser.add_argument(
        "--hub-state-db",
        default=DEFAULT_HUB_STATE_DB,
        type=Path,
        help="absolute SQLite path for durable Edge stream state",
    )
    parser.add_argument(
        "--enable-debug-wss", action="store_true", help="enable authenticated /debug WSS"
    )
    parser.add_argument("--debug-bind", help="WSS debug bind address (HOST:PORT)")
    parser.add_argument(
        "--debug-origin",
        action="append",
        dest="debug_origins",
        help="allowlisted browser Origin; may be repeated",
    )
    parser.add_argument("--debug-server-certificate", type=Path)
    parser.add_argument("--debug-server-private-key", type=Path)
    parser.add_argument("--debug-delivery-db", type=Path)
    return parser


def parse_config(argv: Sequence[str] | None = None) -> RuntimeConfig:
    args = build_parser().parse_args(argv)
    bind = validate_bind(args.bind)
    if args.graceful_stop_seconds <= 0:
        raise ServerConfigurationError("graceful stop timeout must be positive")
    if not args.hub_state_db.is_absolute():
        raise ServerConfigurationError("--hub-state-db must be an absolute path")
    debug_origins = tuple(args.debug_origins or ())
    debug_bind = debug_certificate = debug_private_key = None
    if args.enable_debug_wss:
        missing = [
            name
            for name, value in (
                ("--debug-bind", args.debug_bind),
                ("--debug-origin", debug_origins),
                ("--debug-server-certificate", args.debug_server_certificate),
                ("--debug-server-private-key", args.debug_server_private_key),
            )
            if not value
        ]
        if missing:
            raise ServerConfigurationError(
                "--enable-debug-wss requires explicit " + ", ".join(missing)
            )
        debug_bind = validate_bind(args.debug_bind)
        try:
            DebugRelayConfig(origins=debug_origins)
        except ValueError as exc:
            raise ServerConfigurationError(f"invalid debug WebSocket configuration: {exc}") from exc
        debug_certificate, debug_private_key = (
            args.debug_server_certificate,
            args.debug_server_private_key,
        )
    return RuntimeConfig(
        bind=bind,
        server_certificate_path=args.server_certificate,
        server_private_key_path=args.server_private_key,
        client_ca_certificate_path=args.client_ca_certificate,
        graceful_stop_seconds=args.graceful_stop_seconds,
        hub_state_db_path=args.hub_state_db,
        debug_wss_enabled=args.enable_debug_wss,
        debug_bind=debug_bind,
        debug_origins=debug_origins,
        debug_server_certificate_path=debug_certificate,
        debug_server_private_key_path=debug_private_key,
        debug_delivery_db_path=args.debug_delivery_db,
    )


def read_required_file(path: Path, label: str) -> bytes:
    try:
        content = path.read_bytes()
    except OSError as exc:
        raise ServerConfigurationError(f"cannot read {label} from {path}: {exc}") from exc
    if not content.strip():
        raise ServerConfigurationError(f"{label} file is empty: {path}")
    return content


async def run_server(
    config: RuntimeConfig,
    shutdown: asyncio.Event | None = None,
    *,
    debug_delivery_store: DebugDeliveryStore | None = None,
    debug_server_factory: Any = create_debug_server,
    debug_delivery_db: str | Path | None = None,
    hub_store: HubStore | None = None,
) -> None:
    server_certificate = read_required_file(config.server_certificate_path, "server certificate")
    server_private_key = read_required_file(config.server_private_key_path, "server private key")
    client_ca_certificate = read_required_file(
        config.client_ca_certificate_path, "client CA certificate"
    )
    hub = EdgeHub(hub_store or SqliteHubStore(config.hub_state_db_path))
    if debug_delivery_store is not None and debug_delivery_db is not None:
        raise ServerConfigurationError(
            "provide either DebugDeliveryStore or debug delivery database, not both"
        )
    delivery_store = debug_delivery_store
    if delivery_store is None and debug_delivery_db is not None:
        delivery_store = SqliteDebugDeliveryStore(debug_delivery_db)
    delivery = None
    if delivery_store is not None:
        delivery = DebugGrantDelivery(hub, delivery_store)

    async def handle_debug_event(event: dict[str, object]) -> None:
        if delivery is None:
            raise ServerConfigurationError("debug event delivery is disabled")
        payload = event.get("payload")
        if not isinstance(payload, dict):
            raise SessionError("debug event payload must be an object")
        if event.get("eventType") == "debug.session.grant_requested":
            await delivery.queue_from_event(payload)
        else:
            await delivery.revoke_from_event(payload)

    service = EdgeControlService(
        hub, PeerIdentityVerifier(), handle_debug_event if delivery else None
    )
    server = create_server(
        service,
        bind=config.bind,
        server_certificate=server_certificate,
        server_private_key=server_private_key,
        client_ca_certificate=client_ca_certificate,
    )
    debug_server: Any | None = None
    if config.debug_wss_enabled:
        if delivery_store is None:
            raise ServerConfigurationError(
                "debug WSS is enabled but no production DebugDeliveryStore was provided; "
                "refusing to start fail-open ingress"
            )
        if not all(
            (
                config.debug_bind,
                config.debug_server_certificate_path,
                config.debug_server_private_key_path,
            )
        ):
            raise ServerConfigurationError("debug WSS configuration is incomplete")
        relay = DebugRelay(
            delivery_store,
            EdgeHubDebugTransport(hub),
            config=DebugRelayConfig(origins=config.debug_origins),
        )
        relay.attach_hub(hub)
        debug_server = debug_server_factory(
            relay,
            bind=config.debug_bind,
            server_certificate=config.debug_server_certificate_path,
            server_private_key=config.debug_server_private_key_path,
        )

    shutdown_event = shutdown if shutdown is not None else asyncio.Event()
    loop = asyncio.get_running_loop()
    installed_signals: list[signal.Signals] = []
    if shutdown is None:
        for shutdown_signal in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(shutdown_signal, shutdown_event.set)
                installed_signals.append(shutdown_signal)
            except NotImplementedError:  # pragma: no cover - non-POSIX fallback
                pass

    try:
        await server.start()
        LOGGER.info("edge_hub_ready bind=%s mtls=required", config.bind)
        if debug_server is not None:
            debug_server = await debug_server
            LOGGER.info("debug_wss_ready bind=%s path=/debug tls=required", config.debug_bind)
        await shutdown_event.wait()
    finally:
        LOGGER.info("edge_hub_stopping graceful_timeout_seconds=%s", config.graceful_stop_seconds)
        if debug_server is not None:
            debug_server.close()
            await debug_server.wait_closed()
        await server.stop(config.graceful_stop_seconds)
        for shutdown_signal in installed_signals:
            loop.remove_signal_handler(shutdown_signal)


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    try:
        config = parse_config(argv)
        asyncio.run(run_server(config, debug_delivery_db=config.debug_delivery_db_path))
    except (ServerConfigurationError, SessionError, OSError) as exc:
        LOGGER.error("edge_hub_configuration_error error=%s", exc)
        return 2
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
