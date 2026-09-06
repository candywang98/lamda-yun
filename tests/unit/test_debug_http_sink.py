from datetime import UTC, datetime

import httpx
import pytest
from cloudctl_outbox.debug_http_sink import DebugHubHttpSink
from cloudctl_outbox.sinks import EventEnvelope


@pytest.mark.asyncio
async def test_debug_http_sink_posts_idempotency_headers_and_payload() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["headers"] = dict(request.headers)
        seen["body"] = request.read()
        return httpx.Response(202)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://hub.test")
    sink = DebugHubHttpSink(
        "https://hub.test",
        client_certificate="/unused/client.crt",
        client_private_key="/unused/client.key",
        ca_certificate="/unused/ca.crt",
        client=client,
    )
    try:
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
    finally:
        await client.aclose()
    assert seen["headers"]["x-cloudctl-event-id"] == "evt-1"
    assert b'"eventType":"debug.session.revoked"' in seen["body"]


def test_debug_http_sink_rejects_plaintext_endpoint() -> None:
    with pytest.raises(ValueError, match="HTTPS"):
        DebugHubHttpSink(
            "http://hub.test",
            client_certificate="a",
            client_private_key="b",
            ca_certificate="c",
        )
