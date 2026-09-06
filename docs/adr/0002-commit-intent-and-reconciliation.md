# ADR-0002: Commit intent and reconciliation

Status: Accepted

Date: 2026-08-30

## Decision

Persist a commit intent before the irreversible publish action. Execute the commit activity with one attempt. Any timeout or disconnect transitions the target to `UNKNOWN`; reconciliation may observe state but may not issue another commit.

## Consequences

Operators may need to resolve uncertain results manually, but the system never creates duplicate posts by treating a transport retry as a business retry.

