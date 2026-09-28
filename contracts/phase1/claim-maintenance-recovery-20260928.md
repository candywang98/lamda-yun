# Claim Maintenance Recovery / 20260928.1

## Observed Failure

OnePlus9R v4 updated in place on 2026-09-28 at 14:14:02 UTC. Under the
controller's authorized maintenance window its automatic heartbeat succeeded,
then `/companion/v2/tasks/claim` returned HTTP 409. The process and exact
accessibility binding remained alive, but the sync service disappeared and
the last cloud heartbeat stopped advancing.

The server's existing maintenance denial is HTTP 409 with a JSON string detail:
`device is in maintenance and cannot claim tasks`.
`CompanionSyncService.syncLoop` currently calls `stopSelf()` for any
non-retryable `CloudHttpException`; this stops the independent presence loop.

## Bounded Fix

1. Handle only this exact structured maintenance denial at the claim boundary.
   A maintenance claim is not a successful empty claim or a granted task.
2. Defer the task-loop iteration with bounded existing backoff/delay; do not
   stop the service, drop any queue item, invoke local execution, mutate
   credentials or synthesize a lease.
3. Presence/control synchronization must remain available during maintenance.
   When the server later permits claims, normal admission can resume.
4. Keep 401/403, unrelated 409/422, malformed bodies and errors from other
   endpoints on their existing paths. Do not make all 409 responses retryable.
5. Keep the server maintenance gate and all accessibility/lease/fencing checks.
6. No persistent identity, schema, pin, recipe key, update key or version change.

## Ownership And Verification

Worker writes only `CompanionSyncService.kt`, a focused helper under `service/`
if needed, focused tests under `app/src/test/java/.../service/`, and
`artifacts/three-device-20260928/worker-maintenance.md`.

Required tests: exact structured denial is deferred; missing/wrong detail,
malformed JSON, wrong status and unrelated 409 remain rejected; 401/403 remain
auth errors; no local execution or enqueue/finish occurs for maintenance;
presence remains alive; a later ordinary claim follows normal handling.
Use executable service/call-path coverage, not only an unused classifier test.

Worker uses GPT-5.6 Sol / High in its isolated worktree. No ADB/SSH, real
network, production deployment or device operations. Controller owns version,
APK build/install and real maintenance-enter/exit acceptance.
