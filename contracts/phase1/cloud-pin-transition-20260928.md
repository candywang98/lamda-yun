# Verified Cloud Leaf Transition / 20260928.1

## Verified Incident

On 2026-09-28, both OnePlus9R and Huawei VOG report a validated network but
`Cloud certificate fingerprint mismatch` from the existing pinned transport.
The Huawei and OnePlus7 saved bindings contain the old pin below. The OnePlus9R
binding is not readable in its non-debuggable APK; its mismatch was observed in
the heartbeat log, not inferred to be a specific saved byte value.

Authenticated SSH certificate reads and a public TLS handshake with default
CA/hostname verification independently agree on the current leaf fingerprint.
The server's retained certificate archive verifies the previous leaf.

- Exact host: `43.133.243.154.sslip.io`.
- Old leaf SHA256:
  `fe178c22ba4327c0a71cdd0c7561654fb76ff67c02aa5461f076bf2fc60622d1`.
- Verified successor leaf SHA256:
  `f2a9423e27fd8d6cdcd00d76e9da8918a402e118fe52656b84342dda6fb40725`.
- Old leaf validity: 2026-09-11T18:09:49Z through 2026-12-10T18:09:48Z.
- Successor validity: 2026-09-27T06:21:32Z through 2026-12-26T06:21:31Z.

## Narrow Compatibility Rule

The signed application may embed this reviewed transition. It is not an
automatic trust-on-first-use mechanism and must not learn from network errors.

1. Preserve existing exact enrolled-pin matching.
2. Additionally permit the verified successor only when BOTH the transport's
   actual URI host is exactly the production host above and its configured pin
   is exactly the old leaf above. The successor certificate must be within its
   X.509 validity window. Do not accept a chain member other than the leaf.
3. Other hosts, absent host context, unknown configured pins, unlisted leaves,
   expired/not-yet-valid successor certificates and empty chains fail closed.
4. Apply the same policy to normal HTTP, file downloads and WebSocket TLS.
   Preserve hostname/SNI behavior; never install an always-true hostname
   verifier, disable TLS validation, add HTTP fallback, or trust arbitrary CAs.
5. Do not change stored `certificateSha256`, token, deviceId, accountId or
   bindingId. This preserves `orderConnectionScope` and pending upload identity.
   No re-enrollment, data migration, queue dropping or preference patching.
6. No network feature flags or client/server-controlled bypass. Only a reviewed
   application update can change the allowlisted successor.
7. This is a bounded recovery bridge for one verified certificate rotation,
   not a complete certificate-lifecycle solution. A future unlisted rotation
   still fails closed and remains a release/runbook follow-up.

## Tests And Ownership

Required: unchanged exact-pin success, old pin + verified successor + exact
host success, same successor wrong/absent host rejection, unknown pin/leaf
rejection, leaf-not-intermediate selection, successor validity rejection,
equivalent HTTP/file/WS trust configuration, and unchanged connection-scope
hash for an existing binding.

Owned implementation paths:
`mobile/companion/app/src/main/java/com/company/cloudctl/companion/network/PinnedHttpsTransport.kt`,
a new focused policy/helper in that network directory if justified,
`mobile/companion/app/src/main/java/com/company/cloudctl/companion/live/LiveSessionController.kt`,
focused tests in `app/src/test/java/.../network/`, and
`artifacts/three-device-20260928/worker-c.md`.

Do not change enrollment, persisted identities, build signing/version settings,
schemas, application-update public keys, manifests, or service scheduling.
The controller owns build/version/signature preflight and any device update.
