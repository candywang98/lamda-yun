# CONTROL-LOCK-ORDER: confirmed PostgreSQL reproductions

Date: 2026-09-29.

**REPRO-ONLY. The desired regressions are RED and are not mergeable without a
separately authorized production fix. No production fix is included.**

## Source and ownership

- Frozen source: `7d58f6b28158292722c7d037998163f5fcbfca89`.
- Branch: `agent/sol-control-lock-order-repro-20260929`.
- Worktree: `/Users/wangziheng/Desktop/01-主战场/LAMDA云控系统/sol-ime-picker-20260929`.
- New permanent desired test: `tests/integration/test_fleet_control_lock_order.py`.
- Historical characterization and evidence: this directory only.
- Production, existing fixtures, `tests/load/fleet`, workflow and task ledger are
  unchanged. The unrelated untracked `artifacts/ime-picker-recovery-20260929/`
  and `artifacts/publish-permissions-20260929/` directories are preserved.
- No push, external network, other-chat coordination, devices, deployments,
  publishing, messaging, uploads, key operations or production database access.

## Result

Both previously static hypotheses now have deterministic runtime evidence on
owned local PostgreSQL. Each final historical case and each desired regression
captured SQLSTATE **40P01**, not a timeout or a manufactured application error.

| Scenario | Historical assertion | Desired assertion | Actual HTTP outcomes |
| --- | --- | --- | --- |
| queued Q / retained canceled L: claim vs cancel | PASS | FAIL on 40P01 | claim 500, cancel 200 |
| authorized VIEWING / RUNNING T / AUTO L: take-control vs heartbeat | PASS | FAIL on 40P01 | take-control 500, heartbeat 200 |

Authoritative logs:

- `historical-final.log`: **2 passed in 5.05s**, exit **0**.
- `desired-red.log`: **2 failed in 4.26s**, exit **1**.
- Both use strict RuntimeWarning, ResourceWarning and
  PytestUnraisableExceptionWarning filters. There were no warning/teardown
  failures. The two red failures are exactly the desired no-deadlock assertions.

The historical test lives outside default `testpaths = ["tests"]`. It documents
the frozen defect, not a permanent requirement to keep deadlocking.

## Deterministic schedule and real guards

The fixture starts a fresh loopback-only PostgreSQL cluster and unique database.
Two independently constructed ASGI apps have separate engines/pools. No fixture
accepts an external DSN or reads `DATABASE_URL` / `CLOUDCTL_DATABASE_URL`.
PostgreSQL child-process environments also remove ambient `PG*` settings.

All scenario state is created via natural ASGI endpoints:

- direct simulated device creation and enrollment;
- actual Companion bearer authentication;
- operator dev-test identity with the real permission/tenant dependencies;
- side-effect-free `ui.find` task creation, claim and completion/heartbeat;
- INTERACTIVE_REMOTE session establishment and the real Companion authorization
  acknowledgment endpoint.

There are no direct task/lease-row mutations or mocked service results. These
are ASGI simulated clients, not hardware, production OIDC or network-capacity
acceptance.

The scheduler pauses the first request immediately after its **first acquired
FOR UPDATE row lock**. It starts the second request, reads `pg_blocking_pids`
through an independent observer connection, and releases the first request once
the second is genuinely blocked by it. If a future fix instead lets the second
request finish without waiting, that also releases the first request.

This does not prescribe the first lock's table or require the second request to
hold a lease before requesting a task. Adding a common first lock or moving the
second task lock before its lease can therefore serialize correctly. Only the
historical artifact checks the old inverted sequence. The permanent desired
tests check HTTP success, absence of SQL errors, and durable outcomes.

SQLAlchemy cursor events record real requested/completed statements and
parameters. They also track the actual asyncpg backend PID for every request
statement, including authentication. A future DeviceRow-first fix may cause the
other request to wait during authentication's device UPDATE; the observer must
recognize that wait without demanding a later business-layer lock.
`pg_stat_clear_snapshot()` refreshes the observer's statistics
snapshot before each observation; otherwise `pg_stat_activity.query` can lag
behind the live blocker list. The cluster's default activity-query length can
truncate the long task SELECT in `wait_edge.query`; the cursor trace preserves
the full WHERE/ORDER/LIMIT/FOR UPDATE clause.

The database detector remains at its default **deadlock_timeout = 1s** and
**lock_timeout = 0**. The test has a 12-second outer bound, no sleep-based
scheduling, retries, skipped tests, xfails or changed database lock settings.

## Cycle 1: queued cancel

Natural setup:

1. Create earlier task E, claim it and complete it successfully.
2. Verify E is SUCCEEDED and its AUTO lease L is retained with `canceled_at`.
3. Create Q; verify the only task states are SUCCEEDED and QUEUED, with no active
   task. Q has no task lease and has never been attempted.

Final historical PIDs and observed order:

1. cancel, PID **2819**, acquires `MobileTaskRow(Q) FOR UPDATE`, then pauses.
2. claim, PID **2822**, acquires `DeviceRow(D)` and `DeviceLeaseRow(L)`.
3. claim's active-task SELECT completes with no active task. Its queued-task
   `FOR UPDATE` requests Q and blocks on cancel.
4. Observer confirms `2822 -> 2819`, wait event `Lock / transactionid`.
5. Releasing cancel lets it update Q and request `DeviceLeaseRow(L) FOR UPDATE`.
6. The default detector reports **40P01**. claim returns 500; cancel returns 200.

Actual final durable state:

- E remains unchanged, including its successful result.
- Q is runner `FAILED`, business `CANCELLED`, attempt **0**, without a task lease.
- L is identical to the retained canceled lease from E; no new lease is minted.
- The aborted claim transaction leaves no partial task claim.

Frozen source locations:

- `mobile_service.py:1521`: lease row lock; canceled rows still get locked.
- `mobile_service.py:1531`: active SELECT, empty in this reproduction.
- `mobile_service.py:1551`: queued-task locking SELECT.
- `mobile_service.py:1970`: completion retains the canceled lease row.
- `platform_tasks.py:107`: QUEUED cancellation is allowed.
- `platform_tasks.py:700`: cancel takes the task lock.
- `platform_tasks.py:740` and `:343`: cancel calls the occupation helper, which
  locks L **before** rejecting canceled/foreign leases.

The normal queued heartbeat/finish active-lease guards are irrelevant to this
case: it deliberately uses the valid queued **operator cancel** branch.

## Cycle 2: live take-control

Natural setup:

1. Establish an unexpired INTERACTIVE_REMOTE VIEWING session on app 2.
2. Enrolled Companion acknowledges authorization; `userConfirmedAt` is present
   and the session advertises `allowsInput = true`.
3. Claim a read task through app 1, replacing the VIEWING session's LIVE lease
   with AUTO, then heartbeat it to committed RUNNING.
4. GET the live status through its real token/actor guard and sweep: still
   VIEWING, authorized and unexpired. Verify task and matching AUTO lease are
   both unexpired and uncanceled.

Final historical PIDs and observed order:

1. heartbeat, PID **2830**, acquires `MobileTaskRow(T) FOR UPDATE`, then pauses.
2. take-control, PID **2832**, acquires D and L.
3. take-control's UPDATE of RUNNING tasks requests T and blocks on heartbeat.
4. Observer confirms `2832 -> 2830`, wait event `Lock / transactionid`.
5. Releasing heartbeat lets its valid active-lease path request L.
6. The default detector reports **40P01**. take-control returns 500; heartbeat
   returns 200.

Actual final durable state:

- T remains runner/business RUNNING; its matching AUTO lease is extended.
- L remains AUTO, uncanceled and owned by T.
- The live service remains VIEWING; no REMOTE lease or paused task survives the
  aborted take-control transaction.

Frozen source locations:

- `fleet_live.py:555` / `:754`: sweep does not reject this fresh VIEWING/AUTO state.
- `fleet_live.py:569` / `:571`: take-control locks D then L.
- `fleet_live.py:573`: only a conflicting active REMOTE owner is rejected here.
- `fleet_live.py:585`: UPDATE of RUNNING tasks requires the task row lock.
- `mobile_service.py:1815` / `:1831` / `:1845`: heartbeat locks T, passes the
  active-lease guard, then locks L.

## Relation to the incoming active-claim fix

These tests run only the frozen production source, not Franklin's new branch.
There is no runtime before/after claim-fix comparison in this deliverable.

The observed queued trace shows the active SELECT completing empty before the
actual lease/queued-task cycle. Moving only that empty active SELECT before L
does not remove the observed L-to-Q order. The live concurrent pair contains no
claim request at all; claim occurs only during completed setup. Thus the trace
supports independence from that specific reorder, but integrated rerunning is
still the controller's responsibility. No broader lock contract is proposed.

## Cleanup and limits

- `asyncio.TaskGroup` cancels and drains workers on an unexpected failure or
  outer cancellation before request clients or engines leave scope.
- `AsyncExitStack` closes HTTP clients and lifespans and also explicitly
  disposes engines if schema creation or lifespan entry fails.
- The cluster fixture waits for its own PostgreSQL stop before removing data.
  A stop failure raises and leaves data intact, with any original exception
  retained by normal exception chaining.
- Every final case checks **0 pending transactions**, **0 checked-out
  connections**, and **0 remaining request workers** before returning evidence.
- Both final logs confirm two app-pair teardowns and cluster removal, including
  the run where desired assertions fail.
- A filesystem check confirmed both recorded final cluster roots no longer
  exist after teardown.
- A final process scan found no `postgres.*control-lock-owned-pg` processes.
- No application exceptions were swallowed: ASGITransport renders genuine
  server errors as HTTP 500; the engine's error observer separately captures
  SQLSTATE and detector details.

Environment: macOS 26.0 arm64; main `cloudctl-source/.venv`, Python **3.13.5**;
PostgreSQL **16.15 (Homebrew)**; asyncpg **0.31.0**; SQLAlchemy **2.0.52**;
**AsyncAdaptedQueuePool**, with production engine options unchanged.
Imported `cloudctl_api.__file__` resolves to this worktree, not main.

This proves two reachable software deadlocks on local PostgreSQL. It neither
establishes the cause of earlier SQLite load failures nor measures production
frequency or hardware behavior. Linux/hosted CI has not been run for this item.

## Exact verification commands

All commands run from the worktree above. Environment used for pytest/mypy:

```bash
ROOT="$PWD"
PYTHON="$ROOT/../cloudctl-source/.venv/bin/python"
export PYTHONPATH="$ROOT/services/control-api/src:$ROOT/packages/domain/src:$ROOT/packages/edge-protocol/src:$ROOT/packages/lamda-driver/src:$ROOT/packages/automation-sdk/src:$ROOT/packages/observability/src:$ROOT/services/temporal-worker/src:$ROOT/services/edge-hub/src:$ROOT/services/outbox-dispatcher/src:$ROOT/edge/gateway/src:$ROOT/tests/integration"
```

Historical characterization, exit **0**, **2 passed**:

```bash
"$PYTHON" -m pytest -q -s -p no:cacheprovider \
  -W error::RuntimeWarning -W error::ResourceWarning \
  -W error::pytest.PytestUnraisableExceptionWarning \
  artifacts/control-lock-order-20260929/test_historical_control_lock_order.py \
  > artifacts/control-lock-order-20260929/historical-final.log 2>&1
```

Permanent desired regressions, exit **1**, **2 failed on 40P01**:

```bash
"$PYTHON" -m pytest -q -s -p no:cacheprovider \
  -W error::RuntimeWarning -W error::ResourceWarning \
  -W error::pytest.PytestUnraisableExceptionWarning \
  tests/integration/test_fleet_control_lock_order.py \
  > artifacts/control-lock-order-20260929/desired-red.log 2>&1
```

Static/security checks, all exit **0**:

```bash
../cloudctl-source/.venv/bin/ruff check --no-cache \
  tests/integration/test_fleet_control_lock_order.py \
  artifacts/control-lock-order-20260929/test_historical_control_lock_order.py
../cloudctl-source/.venv/bin/ruff format --check \
  tests/integration/test_fleet_control_lock_order.py \
  artifacts/control-lock-order-20260929/test_historical_control_lock_order.py
MYPYPATH="$PYTHONPATH" "$PYTHON" -m mypy --follow-imports=silent \
  --cache-dir=/tmp/control-lock-order-mypy \
  tests/integration/test_fleet_control_lock_order.py \
  artifacts/control-lock-order-20260929/test_historical_control_lock_order.py
bash scripts/check-security-boundaries.sh
git diff --cached --check
```

Ruff: all checks passed / two files already formatted. Mypy: no issues in two
source files. This is scoped worktree typing with explicit MYPYPATH and silent
dependency following, not a claim of full raw-CI equivalence.

Read-only scope check, exit **0**, no diff:

```bash
git diff --exit-code 7d58f6b28158292722c7d037998163f5fcbfca89 -- \
  services tests/load/fleet tests/integration/test_fleet_two_devices.py .github docs/current
```

Cleanup process scan, exit **1** meaning no matching process:

```bash
ps -axo pid=,command= | rg '[p]ostgres.*control-lock-owned-pg'
```

Earlier tooling iterations: a wrong parent `.venv` lookup exited 127 before
tests started; corrected to `cloudctl-source/.venv`. The first historical smoke
run passed 2 tests in 4.94s. Ruff initially reported three local test-source
issues, subsequently corrected. The preliminary observer log was superseded
by the snapshot-refreshed final log above and is not retained as authoritative
query evidence. An intermediate strict pair was 2 passed in 6.62s / 2 expected
failed in 5.82s. Final verification reran only the same two scenarios after
extending PID observation to authentication-phase lock waits. No broad or
repeated load-suite cycle was run.

## Handoff

Stop at the confirmed reproductions. Separately authorize production ownership
and semantics for the two paths before changing them. The new desired test file
is deliberately red and must not be integrated as a green gate until the
authorized production work makes both scenarios pass without weakened guards.
