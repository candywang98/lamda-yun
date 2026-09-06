# P5-001 evidence summary

- Task: 负载、长稳与资源容量测试
- Audited: 2026-08-31
- Software status: `implemented`
- Acceptance status: `blocked_hardware`

## Implemented local evidence

`scripts/operational-acceptance.py` ran 500 in-process Control API requests at concurrency 16.
All 500 returned HTTP 200 with zero errors. The recorded local metrics were 54.338 requests/s,
p50 266.330 ms, p95 430.609 ms, p99 520.215 ms, and 5,662,782 bytes peak Python allocation.
The configured local regression thresholds passed.

## Remaining acceptance gate

This was a bounded ASGI test, not a long soak or production capacity result. No authorized
physical device, Android/LAMDA/App matrix, production PostgreSQL/Temporal/object store, or real
resource saturation was exercised. P5-001 remains `blocked_hardware` until the hardware evidence
gate validates load, soak, capacity, and telemetry correlation on an authorized physical device.
