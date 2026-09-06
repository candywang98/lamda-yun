# P5-002 evidence summary

- Task: 断网/重启/锁丢失/磁盘压力 Chaos
- Audited: 2026-08-31
- Software status: `implemented`
- Acceptance status: `blocked_hardware`

## Implemented local evidence

The bounded local Chaos harness proved: 25 offline Edge messages persist and replay in order; a
`STARTED` command survives spool close/reopen; a higher fencing token invalidates the previous
lease; and controlled SQLite disk pressure raises `SQLITE_FULL` while a committed sentinel and
`integrity_check=ok` survive. All four local checks passed.

## Remaining acceptance gate

No real network, Edge process, PostgreSQL, Temporal, object store, physical device, or LAMDA lock
was faulted. P5-002 remains `blocked_hardware` until all network outage, Edge restart, lease loss,
disk pressure, and recovery checks are captured through the authorized hardware evidence gate.
