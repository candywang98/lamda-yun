# P1-012 evidence summary

- Task: Mock end-to-end publish closure
- Audited: 2026-08-31
- Software status: `implemented`
- Acceptance status: `pending`

## Implemented closure

- The control API creates an immutable publish snapshot, enforces idempotency, separates submitter and approver, and issues a fencing-bound commit intent.
- The Temporal workflow validates, acquires a lease, stages content, waits for optional approval, writes the commit intent, attempts the commit once, reconciles, cleans up, and releases the lease.
- The development activity backend refuses a second commit using the same intent.
- The Edge mock executor runs the complete automation lifecycle against a scoped fake driver and records a terminal `SUCCEEDED` event.
- Pre-commit cancellation and post-intent uncertainty remain distinct states, so the mock does not hide reconciliation requirements.

## Verification

- Control-plane integration covers idempotency, approval separation, fencing rollover, stale-token rejection, and commit-intent replay.
- Replay-safety tests verify single-attempt commit policy and deterministic workflow source.
- Edge executor tests cover the full automation lifecycle and successful reconciliation.
- The repository Python suite passed 159 tests after these changes.

## Remaining external gates

Acceptance remains pending because the evidence is mock-only. It does not prove a real LAMDA session, authorized account publication, or production Temporal/Edge deployment.
