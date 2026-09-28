# Work Package 1B Evidence

- Date: 2026-09-28
- Work item: legacy order projection guard
- Frozen contract: `contracts/phase1/order-legacy-projection-guard-20260928.md` (`20260928.1`)
- Baseline: `80171144e3032cfac80924151a7d76839b9a20b5`
- Branch: `agent/sol-order-guard-20260928`

## Defect reproduction

Command:

```text
/Users/wangziheng/Desktop/01-主战场/LAMDA云控系统/cloudctl-source/.venv/bin/python -m pytest -q tests/integration/test_order_legacy_guard.py::test_protected_stale_legacy_status_is_rejected_without_mutation
```

Baseline result: exit `1`; `2 failed in 2.05s` (SQLite and disposable PostgreSQL).
Both legacy uploads returned HTTP 201 and changed the protected order from
`COMPLETED` to `AWAITING_SHIPMENT`.

## Implementation evidence

- Legacy admission locks the same `DeviceRow` with `FOR UPDATE` as durable delivery.
- Existing accepted-page replay returns its read-only ACK before projection checks.
- Every new page normalizes keys with the existing upsert rule and checks durable
  projections for the same tenant, device, and platform before any checkpoint,
  page, or order mutation.
- A protected key rejects the whole page with HTTP 409 detail
  `ORDER_DELIVERY_PROTOCOL_REQUIRED`.
- Durable `_upsert_observed_orders` and its server-side generation ordering were
  not changed.

## Verification

```text
/Users/wangziheng/Desktop/01-主战场/LAMDA云控系统/cloudctl-source/.venv/bin/python -m pytest -q -rs tests/integration/test_order_legacy_guard.py
```

Exit `0`; `18 passed, 2 skipped in 8.01s`. The skipped SQLite parameters are
the PostgreSQL-only row-lock serialization cases; both PostgreSQL parameters
passed.

```text
/Users/wangziheng/Desktop/01-主战场/LAMDA云控系统/cloudctl-source/.venv/bin/python -m pytest -q -rs tests/integration/test_order_legacy_guard.py tests/integration/test_fleet_orders_pagination.py tests/integration/test_order_checkpoint_runs.py tests/integration/test_order_delivery.py tests/integration/test_orders_sync.py
```

Exit `0`; `115 passed, 3 skipped in 39.58s`. All skips are SQLite parameters
for PostgreSQL row-lock concurrency tests.

```text
/Users/wangziheng/Desktop/01-主战场/LAMDA云控系统/cloudctl-source/.venv/bin/python -m pytest -q -rs 'tests/integration/test_order_legacy_guard.py::test_postgres_durable_admission_serializes_legacy_guard[postgres]' 'tests/integration/test_order_legacy_guard.py::test_postgres_legacy_admission_can_precede_durable_projection[postgres]' 'tests/integration/test_order_delivery.py::test_postgres_concurrent_creation_and_receipt_replay[postgres]'
```

Exit `0`; `3 passed in 3.10s` against disposable PostgreSQL.

```text
/Users/wangziheng/Desktop/01-主战场/LAMDA云控系统/cloudctl-source/.venv/bin/ruff format --check services/control-api/src/cloudctl_api/fleet_orders.py tests/integration/test_order_legacy_guard.py
/Users/wangziheng/Desktop/01-主战场/LAMDA云控系统/cloudctl-source/.venv/bin/ruff check services/control-api/src/cloudctl_api/fleet_orders.py tests/integration/test_order_legacy_guard.py
/Users/wangziheng/Desktop/01-主战场/LAMDA云控系统/cloudctl-source/.venv/bin/mypy services/control-api/src/cloudctl_api/fleet_orders.py
/Users/wangziheng/Desktop/01-主战场/LAMDA云控系统/cloudctl-source/.venv/bin/pyright --pythonpath /Users/wangziheng/Desktop/01-主战场/LAMDA云控系统/cloudctl-source/.venv/bin/python services/control-api/src/cloudctl_api/fleet_orders.py
git diff --check
```

All commands exited `0`. Pyright printed a non-failing warning that the worktree
has no local `.venv` subdirectory; the explicit shared interpreter was used and
the result was `0 errors, 0 warnings`.

## Coverage and gaps

Covered: protected stale status, protected missing fields, mixed-page rollback,
protected-page error precedence, accepted legacy replay without mutation,
same key in another tenant/device, normal legacy compatibility, durable
generation ordering, and PostgreSQL same-device admission serialization.
Both durable-first and legacy-first lock acquisition orders are covered.

No database concurrency gap remains for this work package. No migration,
generated client, shared task source, device, production database, SSH,
deployment, or push operation was performed.
