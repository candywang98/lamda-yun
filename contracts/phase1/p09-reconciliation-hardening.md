# P09 reconciliation hardening — contract p09-reconcile/20260910.1

Baseline `6826a44`. This slice hardens existing uncertainty guards; it does not enable business-side-effect recipes or certify G3.

## Control lane

RECONCILING is absorbing for ordinary device/operator events until explicit evidence-based `PlatformTaskService.reconcile`. Device heartbeat, later STEP/LOG events, ordinary RESUME_CHECK/PAUSED events, ordinary finish, pause/cancel/retry must not silently convert uncertainty to runnable, successful or safely failed state. Preserve event sequence/idempotency and ownership/lease validation; reject illegal state-changing transitions with 409, or retain reconciliation for non-mutating telemetry. Explicit reconcile is the only business-state exit. Terminal task event delivery cannot reopen terminal state. Existing successful idempotent terminal retry response stays valid.

Owned: services/control-api/**, tests/integration/**. No schema expansion, migration or generated-client changes required for this slice. Do not weaken result validation or assume a boolean is evidence. Disposable SQLite/PostgreSQL tests only.

## Android lane

Existing IrreversibleActionGate and IrreversibleActionCoordinator must fail closed on uncertainty. Persist a local RECONCILING state, not an ordinary runnable/paused or terminal-success state. Local task selection, resume enqueue, lease renewal/re-enqueue, restart, and Recipe activation must not release this state or repeat action. UNKNOWN/INTENT remains blocked; no implicit marking APPLIED from an unverified callback return in production-facing defaults. Explicit confirmation must be supplied by a caller that actually verified the postcondition. Cancellation after intent conservatively records UNKNOWN and preserves coroutine cancellation semantics; no swallowed cancellation that lets execution continue. An APPLIED repeat never invokes the callback; changed identity/hash is rejected. No real Recipe/service business action is enabled in this slice.

Owned: mobile/companion/**. Tests should cover actual SQLite reopen and repeat, identity mismatch, interrupted action and local head blocking. No production device operations by child. Keep P14 behavior passing. Root owns integration and device.

## Root continuation

Inspect how real signed graph commitActionId/postcondition, immutable task parameters and explicit approval should connect to this gate; separately define the next integration slice after these invariants pass. Until that wiring and per-action fault acceptance are complete, G3 remains NOT ACCEPTED. No real listing publish, money operation or deletion is part of this slice.
