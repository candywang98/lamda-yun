"""Outbox dispatcher entry point."""

from __future__ import annotations

import asyncio
import os

from cloudctl_api.db import Database
from cloudctl_api.settings import Settings
from cloudctl_observability import configure_logging

from .debug_grpc_sink import DebugHubGrpcSink
from .debug_http_sink import DebugHubHttpSink
from .dispatcher import OutboxDispatcher
from .operation_sink import OperationExecutionSink
from .sinks import FanoutSink, LoggingSink
from .store import OutboxStore


async def main() -> None:
    configure_logging()
    settings = Settings()
    database = Database(settings)
    if settings.auto_create_schema():
        await database.create_schema()
    operation_sink = OperationExecutionSink(database, settings)
    debug_sink = _build_debug_sink_from_environment()
    try:
        sinks = [LoggingSink(), operation_sink]
        if debug_sink is not None:
            sinks.append(debug_sink)
        dispatcher = OutboxDispatcher(
            OutboxStore(database),
            FanoutSink(*sinks),
            poll_seconds=settings.event_poll_seconds,
        )
        await dispatcher.run()
    finally:
        await operation_sink.close()
        if debug_sink is not None:
            await debug_sink.close()
        await database.dispose()


def _build_debug_sink_from_environment() -> DebugHubGrpcSink | DebugHubHttpSink | None:
    """Build the production sink only when all mTLS settings are present."""
    target = os.environ.get("CLOUDCTL_DEBUG_HUB_GRPC_TARGET")
    url = os.environ.get("CLOUDCTL_DEBUG_HUB_URL")
    if target and url:
        raise RuntimeError("configure either gRPC target or HTTPS URL, not both")
    identity = {
        "client_certificate": os.environ.get("CLOUDCTL_DEBUG_HUB_CLIENT_CERTIFICATE"),
        "client_private_key": os.environ.get("CLOUDCTL_DEBUG_HUB_CLIENT_PRIVATE_KEY"),
        "ca_certificate": os.environ.get("CLOUDCTL_DEBUG_HUB_CA_CERTIFICATE"),
    }
    configured = [bool(value and value.strip()) for value in (target, url, *identity.values())]
    if not any(configured):
        return None
    if not (target or url) or not all(value and value.strip() for value in identity.values()):
        raise RuntimeError(
            "a Debug Hub endpoint and all mTLS certificate paths are required together"
        )
    kwargs = {key: value for key, value in identity.items() if value is not None}
    if target:
        return DebugHubGrpcSink(
            target,
            **kwargs,  # type: ignore[arg-type]
            server_name=os.environ.get("CLOUDCTL_DEBUG_HUB_SERVER_NAME"),
        )
    return DebugHubHttpSink(url or "", **kwargs)  # type: ignore[arg-type]


if __name__ == "__main__":
    asyncio.run(main())
