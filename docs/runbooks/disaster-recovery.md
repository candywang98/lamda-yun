# Disaster recovery

PostgreSQL stores business truth, Temporal stores workflow history, and S3-compatible storage
contains immutable artifacts and evidence. Recovery requires all three stores at a mutually
consistent recovery point. Target objectives are RPO at most 15 minutes and RTO at most 4 hours,
measured from production-like drills rather than configuration alone.

## Preconditions

- Approved incident/change ticket and named recovery commander.
- Isolated restore environment with scheduling and external device commands disabled.
- Backup manifests, versions, encryption/key access, immutable checksums, and retention policy.
- Known PostgreSQL migration revision, Temporal deployment/build compatibility, and object version.

## Restore sequence

1. Restore all three stores into isolation and verify every checksum before use.
2. Apply database migrations and validate tenant isolation.
3. Restore Temporal visibility/history using the deployment-specific procedure.
4. Validate object hashes referenced by snapshots, APK artifacts, and evidence records.
5. Start the control plane with scheduling disabled.
6. Reconnect one authorized test Edge, run read-only probes, and reconcile `COMMITTING` or
   `UNKNOWN` targets without repeating `commit_once`.
7. Verify audit correlation, SLO telemetry, alert delivery, and export integrity.
8. Re-enable scheduling only through an approved change after smoke and audit checks pass.

## Local workflow check

```bash
.venv/bin/python scripts/operational-acceptance.py --task P5-005
```

This creates a synthetic three-store recovery set, verifies restored digests, and proves that a
corrupted artifact is rejected. Its measured time is not a production RTO and its files are not a
backup. Production acceptance requires real backup snapshots, restore logs, RPO/RTO timestamps,
service smoke results, reconciliation evidence, and an approved re-enable decision.

## Abort and rollback

Abort on checksum mismatch, missing store/version, cross-tenant visibility, incompatible workflow
history, unexplained commit state, or incomplete evidence. Keep the failed restore isolated and
preserve logs. Do not point production traffic at it; return to the last known good environment or
repeat from a verified recovery point.
