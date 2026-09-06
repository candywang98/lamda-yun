# Production debug relay wiring

The debug relay is intentionally fail-closed until the control-plane outbox
has a durable, authenticated delivery channel. The Edge Hub gRPC listener on
`7443` is mTLS-only; it must not be treated as the browser WebSocket endpoint.

## Required deployment pieces

1. Prefer `DebugHubGrpcSink` through `CLOUDCTL_DEBUG_HUB_GRPC_TARGET` and the
   existing Edge Hub mTLS port. Configure a dedicated client certificate whose
   common name starts with `control:`. The legacy HTTPS sink remains optional.
2. Configure the Edge Hub ingress to accept only that client certificate and
   only `POST /internal/v1/debug-events`.
3. The ingress must verify `eventId`, `eventType`, tenant/aggregate binding,
   and reject unknown event types. It must deduplicate by `eventId` before
   queueing `DebugGrantDelivery.queue_from_event` or
   `DebugGrantDelivery.revoke_from_event`.
4. Keep the browser WSS listener disabled until the durable store is wired to
   the same delivery records. Never enable WSS with only
   `InMemoryDebugDeliveryStore` in production.

The gRPC dispatcher variables are:

- `CLOUDCTL_DEBUG_HUB_GRPC_TARGET`
- `CLOUDCTL_DEBUG_HUB_SERVER_NAME` when DNS/TLS name differs from the target
- `CLOUDCTL_DEBUG_HUB_CLIENT_CERTIFICATE`
- `CLOUDCTL_DEBUG_HUB_CLIENT_PRIVATE_KEY`
- `CLOUDCTL_DEBUG_HUB_CA_CERTIFICATE`

## Secret handling

Relay bearer tokens may occur only in the protected grant event body in
memory. They must not be placed in URLs, headers, audit metadata, logs, or
retry state. Revocation events intentionally contain no bearer token.

## Verification checklist

- mTLS client certificate is required and validated against the configured CA.
- A duplicate `eventId` produces no second Edge queue entry.
- A revoked session is rejected by WSS before command forwarding.
- WSS accepts only `debug.auth` as the first frame and responds with `ready`.
- Browser traffic cannot reach device port `65000` or any raw socket.
