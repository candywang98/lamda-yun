# Performance and capacity verification

## Local gate

```bash
.venv/bin/python scripts/operational-acceptance.py --task P5-001 \
  --requests 500 --concurrency 16
```

The generated `artifacts/tasks/P5-001/local-load-report.json` records request count, concurrency,
throughput, p50/p95/p99 latency, error rate, and peak Python allocation. The gate is deliberately
small and repeatable; it detects regressions but is not a production capacity claim.

## Authorized environment gate

Before acceptance, record the authorization ticket, build/version identifiers, topology,
PostgreSQL/Temporal/object-store sizing, Edge/device/LAMDA/App versions, traffic model, and a
correlation ID. Run warm-up, stepped load, peak load, and a soak long enough to expose leaks.

Stop immediately on unknown commit results, fencing rejection, duplicate irreversible action,
loss of required evidence, tenant leakage, device thermal/storage safety limits, or error-budget
exhaustion. Capture CPU, memory, database pool wait, outbox lag, spool bytes, ACK latency,
heartbeat age, evidence completeness, and resource saturation.

P5-001 remains `blocked_hardware` until `scripts/validate-hardware-evidence.py` accepts a physical
device bundle containing `load.authorized_device`, `soak.authorized_device`,
`capacity.resources`, and `telemetry.correlation` checks.
