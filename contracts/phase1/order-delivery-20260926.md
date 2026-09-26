# Durable order delivery, order-delivery/1

Controller baseline: `335de35`. D-12 applies: production runs on Companion and
cloud, no USB/wireless ADB, Edge or development computer dependency.
No real device tasks, publishing, messaging or trade actions during development.

## Ownership

- Controller: Control API models/services/routes, migration 0035, backend tests,
  generated contracts, current plan, integration and deployment.
- Android worker: order-specific persistence/delivery code and tests;
  AutomationStore, LocalAutomationExecutor, CloudCtlAccessibilityService,
  CompanionSyncService and CloudTaskClient integration. No unrelated IM,
  publish, upgrade or control-plane behavior changes.
- Web worker: OrdersView.vue, orders API/helper and focused tests. No unrelated
  operation pages, generated contracts or authoritative docs.
- All writing branches start at the commit containing this frozen contract.
  Worker test evidence belongs in ignored local cache; controller publishes
  final evidence. No browser space18 takeover or external actions.

## Negotiation and task identity

- Optional top-level heartbeat `orderDeliveryProtocol: "order-delivery/1"`.
  Only business Companion advertises this, never heartbeat diagnostic builds.
  Server replaces the stored capability on each heartbeat, including clearing
  it when absent. New tasks and claims require the current capability.
- `/companion/v2/tasks/claim` additionally accepts optional
  `orderDeliveryProtocol: "order-delivery/1"`. New APK sends it on every claim.
  A claim without it cannot receive a durable task, even if a stale heartbeat
  advertised support. No changes to legacy callers' required fields.
- New Web collect request adds `orderDeliveryProtocol: "order-delivery/1"` to
  existing deviceId/direction/maxRows/screens. Requests without it retain
  legacy v1/v2 behavior. New Web never silently falls back to legacy.
- Server resolves exactly one active BOUND Xianyu account for the device and
  freezes accountId/bindingVersion and active mobile binding ID. Missing,
  ambiguous, revoked or incompatible identities fail before task creation.
- Run/task metadata is installed atomically with task creation, not after a
  claimable task is committed. New protocol gets its own idempotency namespace.
- SAME-key replay of an accepted request returns the original run/task and
  identity without resolving the current account. Changed request fields
  conflict. Concurrent requests create at most one task.
- Claim exposes existing accountId/bindingVersion plus:
  `orderDelivery: {protocolVersion, mobileBindingId, direction, maxScreens}`.
  This is immutable execution identity. Missing fields fail closed on Android.
- The existing approved read-only steps remain unchanged. Single and multi
  screen durable tasks both use only the new screen channel, no legacy batch
  dual-write.

## Immutable upload envelope

POST `/companion/v2/orders/delivery`, authenticated by normal Companion binding:

```json
{
  "protocolVersion": "order-delivery/1",
  "taskId": "task UUID",
  "kind": "SCREEN",
  "screen": 1,
  "payloadJson": "immutable serialized JSON",
  "payloadSha256": "lowercase sha256 of exact UTF-8 payloadJson bytes"
}
```

`kind` is SCREEN or COMPLETE. A SCREEN ordinal is 1..3 (and no more than the
task's requested bound); COMPLETE uses ordinal 0. Payload text is bounded at
200000 bytes. Retrying preserves exact bytes and digest, including timestamp.

SCREEN payload is the existing FleetOrderScreenIn:
runKey=taskId, accountKey=accountId, schemaVersion=1, screen, direction, rows,
partialRows, collectedAt. Rows use the existing snake_case OrderIn fields.
All row directions must match. Empty visible pages still produce a screen.

COMPLETE payload:
`{runKey, accountKey, direction, totalScreens, stopReason}`.
totalScreens is the actual persisted number (1..3), not the requested maximum.
stopReason is PLAN_FINISHED, STOP_EMPTY_PAGE, STOP_STAGNANT or STOP_MAX_SCREENS.
Cancellation/failure does not fabricate a COMPLETE marker.

Response (201 first acceptance, 200 exact replay):
`{protocolVersion, taskId, kind, screen, payloadSha256, accepted: true, replayed}`.
The client validates every identity field before acknowledging locally.

Server behavior:
- Check authenticated tenant/device/mobile binding, frozen task/account binding,
  protocol, direction and screen bounds. Require the task to have started.
  Data delivery is independent of execution lease expiry; terminal tasks may
  deliver retained data but must not execute again.
- Serialize by device/task; receipt insertion, order upsert and page summary are
  one transaction. Unique receipt identity is tenant/task/kind/screen.
- Same identity and digest replays without duplicate writes; a different digest
  conflicts and must not replace the original page. Record a conflict indicator
  on the existing receipt so delivery cannot appear successful afterward.
- Screens are contiguous from 1 per task. COMPLETE is accepted only after all
  1..N screens and no extras. A sealed run rejects additional screens.
- New protocol never passes through the legacy checkpoint shared across runs.
  Legacy screens endpoint rejects new-protocol tasks.
- Preserve existing historical rows; no guessed account reassignment. This
  slice freezes task/upload ownership; full legacy order-row account partition
  migration remains a separate known limitation.

## Android persistence, recovery and retry

- Persist immutable screen envelope, step identity, recoverable order state and
  corresponding read-success journal/event in one AutomationStore transaction,
  before another swipe. Replay the saved read, never replace its payload.
- Persist completion marker in the same local transaction as reporting
  collection task success. Failure/cancel/pause never fabricates COMPLETE.
- A dedicated order outbox retains unacknowledged records across process death.
  No generic event-outbox "discard as delivered" fallback. Do not delete records
  on cancel, logout, network failure or malformed response.
- Deliver SCREENs in ordinal order, COMPLETE last. One blocked run must not
  block unrelated runs/devices. Sender is independent of UI navigation and
  execution lease; network retry never replays device actions.
- Retry connection errors, 429 and 5xx with bounded backoff. Identity/409 and
  other permanent 4xx block the record/run for inspection. 401/403 retain data
  and pause pending reauthentication; never silently switch credential scope.
  Malformed ACK is
  unconfirmed, not success. Do not log payload, credentials or account content.
- Bind outbox to the original connection identity (hashed credential scope is
  acceptable); re-enrollment must not send old data under a new identity.
- Restore ordinals, seen registry and page summaries from persisted reads;
  a second screen never becomes screen 1 after resume. Missing/inconsistent
  persisted state blocks resumption.
- Existing physical-page resume validation still applies. If the actual page
  cannot be established after process death, pause safely. Reliable upload
  recovery is required; speculative automatic UI navigation recovery is not.
- Legacy behavior and existing API payload goldens remain compatible.

## Operator result contract

POST collect and GET run add:

```json
{
  "delivery": {
    "protocolVersion": "order-delivery/1",
    "state": "PENDING",
    "receivedScreens": [],
    "expectedScreens": null,
    "collectionComplete": false,
    "stopReason": null
  }
}
```

- PENDING until a valid completion receipt plus its contiguous screens exist
  AND task state is SUCCEEDED. Then SYNCED.
- expectedScreens is the accepted completion total, otherwise null.
- Task FAILED/CANCELLED/EXPIRED/RECONCILING or changed mobile/account binding or
  recorded payload conflict produces BLOCKED; stopReason respectively
  TASK_FAILED/TASK_CANCELLED/TASK_EXPIRED/COLLECTION_RECONCILING/
  MOBILE_BINDING_CHANGED/ACCOUNT_BINDING_CHANGED/PAYLOAD_CONFLICT.
- Legacy runs return protocolVersion=null, state=LEGACY_UNVERIFIED; never infer
  delivery success from their task success. New requests receiving missing or
  incompatible delivery metadata are protocol failures, not legacy success.
- Web distinguishes collection state and synchronization state. Durable PENDING
  continues bounded/backoff polling even when allTerminal=true, with manual
  GET refresh after polling budget expires. Refresh never creates tasks.
- Snapshot request/key while pending, reject double submissions, retain key for
  ambiguous retries and validate returned run/task identity. No retry of an
  accepted collection, only delivery polling.

## Acceptance

Backend: SQLite + disposable PostgreSQL, account/binding/capability gates,
same-key replay, conflicting payload, ACK loss/replay, same/different task
concurrency, screen gaps, final marker, terminal states, tenant/device isolation,
legacy compatibility, migration up/down/re-up and data preservation.

Android: database reopen and fault boundaries, storage-before-success/scroll,
single/multi screen protocol selection, no legacy dual-write, immutable retry,
ACK mismatch, 503/429, binding change, blocked-run isolation, restored second
screen ordinal and incomplete physical recovery fail-closed. Debug/acceptance
unit suites and build; no phone operations.

Web: collection-success/delivery-pending, SYNCED proof, BLOCKED, legacy unknown,
capability/account rejection, malformed success, double clicks, same-key retry,
poll budget, refresh, request races and unmount cleanup.

Software/deployment acceptance never substitutes for the final three-phone
ADB-disconnected business verification.
