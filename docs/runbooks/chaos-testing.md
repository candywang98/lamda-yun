# Chaos testing

## Local gate

```bash
.venv/bin/python scripts/operational-acceptance.py --task P5-002
```

The local suite uses temporary data only. It proves ordered offline replay, command persistence
across Edge spool reopen, stale-lease rejection after a higher fencing token, and fail-closed
SQLite disk-full handling with integrity verification.

## Authorized environment scenarios

1. Network outage: isolate an authorized Edge outbound link; verify commands remain durable,
   replay in order, and no cloud component connects to device port 65000.
2. Edge restart: restart during a reversible step and during evidence upload; verify a single
   runner resumes or reconciles without duplicate commit.
3. Lock loss: expire or supersede the lease; verify the old runner stops writes and the fencing
   rejection is paged.
4. Disk pressure: fill the designated Edge data filesystem within an approved quota; verify new
   work is refused, committed spool data remains readable, and cleanup follows the runbook.
5. Recovery: restore connectivity/capacity, reconcile uncertain state, and prove audit/evidence
   continuity by correlation, workflow, and device IDs.

Never inject these faults into an unapproved device or production tenant. P5-002 remains
`blocked_hardware` until the hardware evidence gate validates all five scenario checks.
