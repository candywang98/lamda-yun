# FLEET-POSTGRES-LIFECYCLE - 2026-09-29

## Scope

- Frozen baseline: `7d58f6b28158292722c7d037998163f5fcbfca89`.
- Branch: `agent/sol-fleet-postgres-lifecycle-20260929`, created directly from
  the frozen baseline in the existing `sol-ime-picker-20260929` worktree.
- Changed files: `tests/load/fleet/harness.py`, `test_fleet_load.py`,
  `test_harness_diagnostics.py`; new `postgres.py`, `test_postgres.py`,
  `test_harness_lifecycle.py` in that directory; this summary.
- Production services/DB/settings/lifespan, workflow, task ledger, mobile,
  and other artifacts remain unchanged. Both pre-existing untracked artifact
  directories are preserved.
- No push, other-chat, device, SSH/ADB, production network, deployment, real
  business operation, installation, or key change. All database writes are
  test fixtures against newly created loopback-only PostgreSQL clusters.
- The final handoff reports the commit SHA containing this summary.

## Evidence and Causality

Controller-supplied hosted evidence, not fetched by this worker:

- Run `36567021427`, commit `7d58f6b`, Python job `109401339980`, completed
  `2026-09-29T12:28:32Z`: **1 failed, 1625 passed, 14 skipped, 33 warnings
  in 651.34s**.
- The only failing node was the 100-client fleet load test. A claim request
  failed in authentication's query-triggered autoflush of
  `mobile_binding.last_seen_at` with SQLite `database is locked`.
  Cleanup subsequently emitted event-loop-closed warnings.
- The earlier hosted `eb1eedc` full pytest run passed **1624 / skip 14**.

This SQLite lock failure is distinct from the earlier, still-unproven 12/20
remote symptom. Historical StaticPool isolation red evidence remains
historical; it is not a reproduction of this file-backed SQLite busy failure
or a PostgreSQL production defect.

Read-only review covered the existing PostgreSQL fixture in
`tests/integration/test_fleet_two_devices.py`, settings/database construction,
and app lifespan. PostgreSQL settings do not automatically create the schema.
The production lifespan owns database disposal only after successful entry.
The independent same-device lock-order investigation is outside this change;
these load results neither establish its causality nor resolve it.

## Implementation

### Owned PostgreSQL Only

`FleetLoadApp` now always starts a `FleetPostgres` context. There is no SQLite
mode, external DSN argument, optional dependency skip, or fallback.

- Discover executable `initdb`, `pg_ctl`, and `createdb` from PATH before
  allocating a cluster. Missing tools raise a specific required-test error.
- Create a test-owned temporary directory, free loopback port, `fleettest`
  role, and UUID database name. The server listens only on `127.0.0.1`, with
  Unix sockets disabled.
- Remove ambient `PG*`, `DATABASE_URL`, and `CLOUDCTL_DATABASE_URL` from tool
  environments. Pass explicit host/port/user/database arguments and an
  explicit `postgresql+asyncpg://` URL to `Settings`, with `env=test`,
  `repository_mode=postgresql`, `object_store_mode=memory`,
  and `dev_auth_bypass=True`.
- Explicitly await `database.create_schema()` before entering app lifespan.
  If schema creation or lifespan entry raises/cancels, await `dispose()`
  before closing the cluster context.
- On normal exit or a body error: close HTTP client, exit app lifespan and
  dispose its engine, then stop the owned cluster and remove its data.
- Startup failures after initialization, server start, or database creation
  stop any started owned server and remove test data. If stopping itself
  fails, do not delete its data; preserve the original exception context.
  Tool subprocesses have bounded startup/shutdown deadlines, not load,
  HTTP, pool, or claim-timeout adjustments.

The production `Database` constructor, pool settings, auth updates, and
lifespan are untouched.

### Structured Workers

Replace the single unstructured `asyncio.gather` with `asyncio.TaskGroup`.
All workers are still created concurrently. On a worker error or caller
cancellation, siblings are cancelled and awaited before the harness exits.
The original exception remains an exception-group leaf; cancellation remains
`CancelledError`. No failure is converted to a successful result.

Preserved: 2x20 baseline, 100 clients, one worker per simulated device,
guard limits, existing pacing/backoffs and retry count, p95 thresholds
**5s / 2s**, original transaction-isolation barriers, durable completion
reconciliation, guard diagnostics, intentional stranded-device behavior,
and UNKNOWN evidence retention. The 100-client test additionally checks
each persisted task is successful and no work remains.

Reports identify `temporary-postgresql`, the actual `asyncpg` driver,
`AsyncAdaptedQueuePool` class and server version, and explicitly limit claims
to simulated in-process ASGI clients against an owned local database.

## Regression Proof

### Frozen Lifecycle Red

Before editing the frozen harness, add the final lifecycle regression and run:

```sh
"$PYTHON" -m pytest -q tests/load/fleet/test_harness_lifecycle.py --show-capture=no
```

**1 failed, 1 passed in 1.43s; exit 1.** The worker-error case failed at:

```text
assert drained_at_close == [True]
actual: [False]
harness resources closed before sibling workers drained
```

Both simulated claim workers enter controlled event barriers. One throws the
sentinel failure while the other's cancellation cleanup is held. The test
records worker completion at the beginning of harness exit, before checking
exception shape. Thus the red is a resource-lifetime assertion, not an
`ExceptionGroup` compatibility failure. The old caller-cancellation case
already passed. The test also drains the deliberately broken baseline's
remaining worker so the red run itself does not leak background work.

### Green Coverage

- PG lifecycle plus unchanged claim/completion isolation tests:
  **4 passed in 5.92s**, exit 0.
- Initial PG safety cases: **11 passed in 8.38s**, exit 0.
- Final full fleet suite includes **13 PG safety cases**: missing tools
  (3); failure after initdb/start/createdb (3); dangerous ambient DSNs (1);
  schema/lifespan entry failure and schema cancellation (3); body error (1);
  stop failure during startup/body preserving data and original context (2).
- The external-DSN test rejects an unsafe URL before creating any engine,
  then verifies the actual database name, server data directory, loopback
  listener and empty Unix-socket setting on the owned cluster.
- Engine-disposed-before-cluster-stop ordering is asserted. Successful
  cleanup removes the directory and closes the owned port. Stop-fault tests
  first prove the data and live server remain, then restore real stopping
  in `finally` and verify cleanup.
- HTTP-200-without-durable-success diagnostics, both transaction-isolation
  tests, event persistence, 100-client/HOL limits and evidence retention
  remain active.

## Final Local Verification

Environment: macOS **26.0 arm64**, Python **3.13.5** from main
`cloudctl-source/.venv`, PostgreSQL **16.15 (Homebrew)** binaries at
`/opt/homebrew/bin/{initdb,pg_ctl,createdb}`, asyncpg **0.31.0**,
SQLAlchemy **2.0.52**, pytest **9.1.1**, pytest-asyncio **1.4.0**,
Ruff **0.16.5**, mypy **2.3.1**.

Commands run from the assigned checkout with:

```sh
ROOT="$(git rev-parse --show-toplevel)"
PYTHON="$ROOT/../cloudctl-source/.venv/bin/python"
export PYTHONPATH="$ROOT/packages/domain/src:$ROOT/packages/edge-protocol/src:$ROOT/packages/lamda-driver/src:$ROOT/packages/automation-sdk/src:$ROOT/packages/observability/src:$ROOT/services/control-api/src:$ROOT/services/temporal-worker/src:$ROOT/services/edge-hub/src:$ROOT/services/outbox-dispatcher/src:$ROOT/edge/gateway/src"
```

The verification runner allocated a fresh `tempfile.mkdtemp` root for each
pytest process and exported that root as `TMPDIR`. Exact pytest subprocess
arguments, with `RUN_ROOT` standing for that generated directory:

```sh
TMPDIR="$RUN_ROOT" "$PYTHON" -m pytest -q tests/load/fleet --show-capture=no \
  -W error::pytest.PytestUnraisableExceptionWarning \
  -W error::pytest.PytestUnhandledThreadExceptionWarning \
  -W error::RuntimeWarning --basetemp "$RUN_ROOT/pytest"
```

**29 passed in 43.09s, exit 0; no skips or warnings.**
The runner read the generated reports before cleanup:

| Scenario | Completed | Remaining | Stranded | Unexpected errors | Claim p95 |
| --- | --- | --- | --- | --- | --- |
| 2x20 | 40 | 0 | 0 | 0 | 0.013199s |
| 100 clients | 100 | 0 | 0 | 0 | 0.684378s |
| HOL healthy device | 10 | 0 | 0 | 0 | 0.022707s |
| HOL failed device | 0 | 9 | 1 | 0 | Not applicable |

Exactly two additional 100-client repetitions used the same warning flags
and a new `TMPDIR` / `--basetemp` per process:

```sh
TMPDIR="$RUN_ROOT" "$PYTHON" -m pytest -q \
  tests/load/fleet/test_fleet_load.py::test_hundred_simulated_clients_control_plane_holds \
  --show-capture=no -W error::pytest.PytestUnraisableExceptionWarning \
  -W error::pytest.PytestUnhandledThreadExceptionWarning \
  -W error::RuntimeWarning --basetemp "$RUN_ROOT/pytest"
```

| Additional repeat | Result | Exit | Claimed / completed | Remaining / errors | Claim p95 |
| --- | --- | --- | --- | --- | --- |
| 1 | 1 passed in 5.00s | 0 | 100 / 100 | 0 / 0 | 0.838830s |
| 2 | 1 passed in 6.17s | 0 | 100 / 100 | 0 / 0 | 0.761218s |

All three report sets identify PostgreSQL server **[16, 15]**, driver
**asyncpg**, pool **AsyncAdaptedQueuePool**. After each pytest process,
the runner checked its root for `fleet-load-pg-*` directories and filtered
`ps -axo pid=,command=` for processes tied to that unique root:
**zero remaining cluster directories and zero remaining processes** in all
three runs. No event-loop-closed output was observed. The runner would retain
data and fail rather than delete a directory tied to a remaining process.

### Static and Security Checks

```sh
"$PYTHON" -m ruff check tests/load/fleet
"$PYTHON" -m ruff format --check tests/load/fleet
MYPYPATH="$PYTHONPATH" "$PYTHON" -m mypy --follow-imports=silent \
  tests/load/fleet/harness.py tests/load/fleet/postgres.py \
  tests/load/fleet/test_fleet_load.py tests/load/fleet/test_harness_diagnostics.py \
  tests/load/fleet/test_harness_lifecycle.py tests/load/fleet/test_harness_isolation.py \
  tests/load/fleet/test_postgres.py
bash scripts/check-security-boundaries.sh
git diff --check
```

All exit **0**. Ruff lint clean, **9 files already formatted**, mypy clean
in **7 source files**, and `Security boundary checks passed.`

An exploratory directory-wide scoped mypy command
(`MYPYPATH="$PYTHONPATH" "$PYTHON" -m mypy --follow-imports=silent tests/load/fleet`)
still exits **1** with **7 existing `object`-not-indexable errors** in
untouched `test_metrics.py` at lines 31, 32, 33, 37, 38, 46, 47 (9 files
checked). Its equality to the frozen baseline was verified with
`git diff --exit-code`; it was not refactored. The seven-file passing command
is intentionally scoped and is not a claim of raw CI mypy equivalence.

## Limits and Handoff

- Hosted CI/Linux on the integrated commit remains for the controller. No
  broad unrelated full-suite cycle was run; hosted results above are supplied
  prior evidence, not a new run by this worker.
- These tests exercise local control-plane behavior with simulated clients,
  not hardware, production capacity, networked multi-node throughput, or
  device readiness. The approved 2+1+1 delivery scope is unchanged.
- No production PostgreSQL failure was observed in these scenarios. The
  separate same-device lock-order investigation is not covered or resolved
  by the one-worker-per-device load results.
- Cleanup tests cover controlled errors and task cancellation, not an
  uncatchable OS kill. A real stop failure intentionally preserves owned
  data and failure context for explicit recovery.
