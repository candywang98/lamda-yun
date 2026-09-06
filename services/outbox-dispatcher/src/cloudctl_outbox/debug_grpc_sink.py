"""mTLS gRPC sink for the Edge Hub ``DeliverDebugEvent`` RPC."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

import grpc
from cloudctl_edge_protocol import edge_control_pb2 as pb
from cloudctl_edge_protocol import edge_control_pb2_grpc as pb_grpc
from google.protobuf.json_format import ParseDict
from google.protobuf.struct_pb2 import Struct

from .sinks import EventEnvelope


class _Stub(Protocol):
    async def DeliverDebugEvent(
        self, request: pb.DebugEventRequest, **kwargs: object
    ) -> pb.DebugEventResponse: ...


class DebugHubGrpcSink:
    """Deliver debug events over the existing client-authenticated gRPC port."""

    def __init__(
        self,
        target: str,
        *,
        client_certificate: str | Path,
        client_private_key: str | Path,
        ca_certificate: str | Path,
        server_name: str | None = None,
        timeout_seconds: float = 15.0,
        stub: _Stub | None = None,
    ) -> None:
        self._channel: grpc.aio.Channel | None = None
        if timeout_seconds <= 0:
            raise ValueError("gRPC timeout must be positive")
        self._timeout_seconds = timeout_seconds
        if stub is not None:
            self._stub = stub
            return
        credentials = grpc.ssl_channel_credentials(
            root_certificates=Path(ca_certificate).read_bytes(),
            certificate_chain=Path(client_certificate).read_bytes(),
            private_key=Path(client_private_key).read_bytes(),
        )
        options = (
            (("grpc.ssl_target_name_override", server_name),) if server_name is not None else ()
        )
        self._channel = grpc.aio.secure_channel(target, credentials, options=options)
        self._stub = pb_grpc.EdgeControlStub(self._channel)  # type: ignore[assignment]

    async def publish(self, event: EventEnvelope) -> None:
        if event.event_type not in {"debug.session.grant_requested", "debug.session.revoked"}:
            return
        payload = ParseDict(event.payload, Struct())
        response = await self._stub.DeliverDebugEvent(  # type: ignore[attr-defined]
            pb.DebugEventRequest(
                event_id=event.id,
                tenant_id=event.tenant_id,
                aggregate_id=event.aggregate_id,
                event_type=event.event_type,
                payload=payload,
            ),
            timeout=self._timeout_seconds,
        )
        if not response.accepted:
            raise RuntimeError(response.detail or "Edge Hub rejected debug event")

    async def close(self) -> None:
        if self._channel is not None:
            await self._channel.close()
