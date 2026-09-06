from datetime import UTC, datetime

import pytest
from cloudctl_edge_protocol import edge_control_pb2 as pb
from cloudctl_outbox.debug_grpc_sink import DebugHubGrpcSink
from cloudctl_outbox.sinks import EventEnvelope


class Stub:
    def __init__(self) -> None:
        self.request: pb.DebugEventRequest | None = None

    async def DeliverDebugEvent(
        self, request: pb.DebugEventRequest, **kwargs: object
    ) -> pb.DebugEventResponse:
        assert kwargs["timeout"] == 15.0
        self.request = request
        return pb.DebugEventResponse(accepted=True)


@pytest.mark.asyncio
async def test_grpc_sink_builds_narrow_debug_event_request() -> None:
    stub = Stub()
    sink = DebugHubGrpcSink(
        "unused",
        client_certificate="unused",
        client_private_key="unused",
        ca_certificate="unused",
        stub=stub,
    )
    await sink.publish(
        EventEnvelope(
            "evt-1",
            "tenant-1",
            "debug_session",
            "session-1",
            "debug.session.revoked",
            {"deviceId": "device-1"},
            datetime.now(UTC),
        )
    )
    assert stub.request is not None
    assert stub.request.event_id == "evt-1"
    assert stub.request.event_type == "debug.session.revoked"
    assert stub.request.payload["deviceId"] == "device-1"
