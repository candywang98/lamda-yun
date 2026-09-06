"""mTLS HTTP event sink for the Edge Hub debug delivery ingress."""

from __future__ import annotations

import json
from pathlib import Path

import httpx

from .sinks import EventEnvelope


class DebugHubHttpSink:
    """Deliver debug events over a private mTLS endpoint.

    The endpoint is intentionally narrow: the server must authenticate the
    client certificate and accept only grant/revoke event envelopes. A 2xx
    response is the delivery acknowledgement; all other responses remain
    retryable in ``OutboxDispatcher``.
    """

    def __init__(
        self,
        base_url: str,
        *,
        client_certificate: str | Path,
        client_private_key: str | Path,
        ca_certificate: str | Path,
        path: str = "/internal/v1/debug-events",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not base_url.startswith("https://"):
            raise ValueError("debug hub endpoint must use HTTPS")
        if not path.startswith("/") or "?" in path:
            raise ValueError("debug hub path must be an origin-relative path")
        self._path = path
        self._owned = client is None
        self._client = client or httpx.AsyncClient(
            base_url=base_url,
            verify=str(ca_certificate),
            cert=(str(client_certificate), str(client_private_key)),
            timeout=15,
            limits=httpx.Limits(max_connections=8, max_keepalive_connections=4),
        )

    async def publish(self, event: EventEnvelope) -> None:
        if event.event_type not in {"debug.session.grant_requested", "debug.session.revoked"}:
            return
        response = await self._client.post(
            self._path,
            headers={"X-CloudCtl-Event-Id": event.id, "X-CloudCtl-Event-Type": event.event_type},
            content=json.dumps(
                {
                    "eventId": event.id,
                    "tenantId": event.tenant_id,
                    "aggregateType": event.aggregate_type,
                    "aggregateId": event.aggregate_id,
                    "eventType": event.event_type,
                    "occurredAt": event.occurred_at.isoformat(),
                    "payload": event.payload,
                },
                separators=(",", ":"),
                ensure_ascii=False,
            ),
        )
        response.raise_for_status()

    async def close(self) -> None:
        if self._owned:
            await self._client.aclose()
