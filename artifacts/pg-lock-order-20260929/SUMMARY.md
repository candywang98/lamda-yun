# PG-LOCK-ORDER

Status: CONFIRMED on test-owned PostgreSQL. REPRO-ONLY, RED, UNMERGEABLE.

- Frozen production source: `7d58f6b28158292722c7d037998163f5fcbfca89`.
- Branch: `agent/sol-pg-lock-order-repro-20260929`.
- Owned writes: `tests/integration/test_mobile_lock_order.py` and this evidence
  directory only. Production code, existing fixtures, workflows, task ledger,
  and `tests/load/fleet/**` remain unchanged.
- Authority: test-owned disposable loopback PostgreSQL only. No external database,
  network queries, deployment, device, key, or real business operations.
- This immutable baseline precedes the controller's separately authorized fix.
  There are no skips, xfails, retries, or production fixes in this snapshot.

## Runtime Result

Final run: **9 passed, 4 failed, 0 errors, 0 skipped**, exit **1**, 15.48 s.
The failures are exactly the four strict desired-no-deadlock regressions.

| Initial state / runner | Characterization victim | Desired-regression victim |
| --- | --- | --- |
| CLAIMED / PREFLIGHT + finish | claim, `40P01`; finish HTTP 200 | claim, `40P01`; finish HTTP 200 |
| CLAIMED / PREFLIGHT + heartbeat | heartbeat, `40P01`; claim HTTP 204 | claim, `40P01`; heartbeat HTTP 200 |
| RUNNING / RUNNING + finish | finish, `40P01`; claim HTTP 204 | claim, `40P01`; finish HTTP 200 |
| RUNNING / RUNNING + heartbeat | claim, `40P01`; heartbeat HTTP 200 | heartbeat, `40P01`; claim HTTP 204 |

Victim selection is not the contract and is not hard-coded. Every forced race
produced one real `asyncpg.exceptions.DeadlockDetectedError`, SQLSTATE `40P01`.
`verified-postgres.log` independently records eight server deadlock reports,
with the conflicting `mobile_task` and `device_lease` SELECT FOR UPDATE queries.
No probe relied on a Python/statement timeout to assert deadlock.

The nine passing cases are four sequential controls, four baseline
characterization cases, and one cancellation/draining case. Final durable state
is read through a new session after both workers terminate:

- An aborted runner leaves task/lease/result/expiry/step data exactly unchanged.
- A surviving finish commits SUCCEEDED/result/completion and cancels its lease
  atomically; a surviving heartbeat commits RUNNING/step 1 and equal task/lease
  expiry. The initial RUNNING control uses step 0.
- Exactly one task and one matching AUTO lease remain; attempt stays 1,
  tenant/device/lease identity and fencing stay consistent.
- Every race has both workers drained, zero pool checkouts, and zero other
  open transactions/lock waiters in that test database.

Machine-readable results: `verified-results.json`. Raw requests, actual SQL,
backend PIDs, error chains and before/after state: `verified.log`. Counts:
`verified-junit.xml`. The earlier draft run remains in `baseline.log`,
`baseline-junit.xml`, and `baseline-postgres.log` (also 9 pass / 4 fail, 15.27 s).

## Source Proof and Scheduling

Frozen paths and one-based lines:

- `services/control-api/src/cloudctl_api/mobile_service.py:728`: bearer
  authentication uses its own UOW before the operation.
- Same file `:1474`, `:1521`, `:1531`: claim locks Device, then DeviceLease,
  then the active MobileTask. `:78` excludes PREFLIGHT/RUNNING from the blocking
  states; `:1540` checks the active lease only after locking the task.
- Same file `:1937`, `:1969`, `:1970`: finish locks task, runs the unchanged
  reply-settlement path, then locks lease.
- Same file `:1814`, `:1845`: heartbeat locks task, then lease.
- `services/control-api/src/cloudctl_api/db.py:1252`: separate sessions and
  `session.begin()` commit/rollback boundaries.

The test obtains a legitimate task and lease using normal ASGI device creation,
enrollment, task creation and claim APIs. Two inert `run.log` steps stay entirely
in the test database; no runner/device is contacted. No row or validation method
is patched to create an impossible state. Operator identity uses the existing
test-mode auth pattern; Companion bearer authentication and business validators
remain real. Enrollment has the normal unnegotiated capability profile; this
does not claim coverage of every negotiated-client gate.

`test_mobile_lock_order.py:345` observes SQL without replacing it. The runner is
paused only AFTER its real task FOR UPDATE returns. On the actual claim's
active-task FOR UPDATE request, a lock snapshot is recorded and the runner is
released. The desired regression does NOT require claim to own lease first.
Only historical characterization asserts that bad acquisition order. A later
approved fix that acquires task first can block at that request and then proceed.
If a different fix removes that observation point, review the scheduling hook;
do not relax the no-deadlock or durable-state assertions.

Production `mobile_service.py` SHA256:
`b026eba59dc3a8bcbd01302eb439c4c00898849c19b6743d8afb7dde21416d1c`.
Final test SHA256:
`dd42cefe3e73d8c5eaee28bc66fe60a468e9f0c6b242a0f11d5682ccc7b66bd3`.
The report labels `7d58f6b...` as `characterization_baseline_sha`, not as a
future tested revision, and records the actual worktree service import path.

## Safety Bounds and Cleanup

- Existing local PostgreSQL 16.15 (Homebrew), asyncpg 0.31.0, SQLAlchemy 2.0.52.
  No installs or global service operations. One new cluster in a pytest-owned
  temporary directory; one new UUID-named database per test.
- Only `127.0.0.1`, a dynamically reserved port, disabled Unix sockets, test user
  `lockorder`. PG connection/service/options environment is removed from tool
  calls. Application environment is cleared and an explicit fixture DSN is used;
  neither `DATABASE_URL` nor `CLOUDCTL_DATABASE_URL` is a fallback.
- The server's reported `data_directory` must exactly match the owned directory.
  Default pool and READ COMMITTED remain unchanged. Normal `deadlock_timeout=1s`,
  `lock_timeout=0`; test-only `statement_timeout=10s`, probe 20 s, drain 5 s,
  PG start/stop 10 s and subprocess 30 s bounds. No random sleeps/retries.
- Finally blocks release barriers, cancel/drain workers, remove hooks, exit
  client/lifespan, dispose engine, then stop only the owned cluster. Partial
  schema/lifespan entry failures still dispose the engine; partial cluster
  startup with an owned PID file still invokes owned-cluster stop.
- Final cluster:
  `/private/var/folders/6b/g5wj9vms7b35lw_73jr6dk940000gn/T/pytest-of-wangziheng/pytest-102/mobile-lock-order-pg0`.
  Server shutdown is in `verified-postgres.log`; `pg_ctl -D <that path>/data status`
  exits **3**, `no server running`; no `postmaster.pid` remains.

Cancellation caveat: deliberate cancellation of in-flight ASGI requests emits
two SQLAlchemy/asyncpg `Exception terminating connection` ERROR logs containing
CancelledError (`verified.log:104`). They are retained, not filtered/suppressed.
The cancellation test still verifies both request workers drained, unchanged
durable state, zero pool checkouts and zero remaining transactions/lock waiters.
There is no `Event loop is closed` log. This is not a claim of silent cancellation
or a diagnosis/fix of all middleware/driver cancellation behavior.

## Commands and Exit Codes

Working directory for all commands:
`/Users/wangziheng/Desktop/01-主战场/LAMDA云控系统/sol-publish-queue-20260929`.
`VENV` below expands to
`/Users/wangziheng/Desktop/01-主战场/LAMDA云控系统/cloudctl-source/.venv`.

```sh
env PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH="$PWD/services/control-api/src:$PWD/packages/domain/src:$PWD/packages/observability/src:$PWD/packages/edge-protocol/src" \
  "$VENV/bin/python" -m pytest -p no:cacheprovider -q -s \
  tests/integration/test_mobile_lock_order.py \
  --junitxml=artifacts/pg-lock-order-20260929/verified-junit.xml \
  > artifacts/pg-lock-order-20260929/verified.log 2>&1
# exit 1: 9 passed, 4 failed, 0 skipped; 15.48 s

"$VENV/bin/ruff" format --check tests/integration/test_mobile_lock_order.py
# exit 0: 1 file already formatted
"$VENV/bin/ruff" check tests/integration/test_mobile_lock_order.py
# exit 0: All checks passed
"$VENV/bin/pyright" \
  --venvpath /Users/wangziheng/Desktop/01-主战场/LAMDA云控系统/cloudctl-source \
  tests/integration/test_mobile_lock_order.py
# exit 0: 0 errors, 0 warnings, 0 informations; pyright-verified.log
bash scripts/check-security-boundaries.sh
# exit 0: Security boundary checks passed
git diff --cached --check -- tests/integration/test_mobile_lock_order.py \
  artifacts/pg-lock-order-20260929/SUMMARY.md
# exit 0: source and summary
git diff 7d58f6b28158292722c7d037998163f5fcbfca89 -- \
  services/control-api/src/cloudctl_api tests/integration/conftest.py \
  tests/load/fleet .github/workflows docs/current/tasks.json
# exit 0; empty diff
```

Initial development checks were not green: Ruff formatting/ASYNC240 was repaired
only in the new test. Targeted Pyright first reported four Pool.checkedout typing
errors; an explicit runtime pool-type assertion fixed them without changing pool
configuration. A subsequent invocation combining `--pythonpath` and `--venvpath`
was rejected with exit 4 (`pyright.log`); the valid final command above uses only
`--venvpath`. Pinned Ruff 0.16.5 and Pyright 1.1.411 were retained; no dependency
upgrade was performed.

The unrestricted staged `git diff --cached --check` exits 2 solely for trailing
spaces in the two verbatim PostgreSQL server logs (SQL formatting emitted by the
server). Those raw evidence bytes are preserved, not rewritten or exempted with
configuration. Source/summary whitespace checks above pass.

## Limits and Handoff

Confidence is high for this reproducible same-device transaction lock cycle on
the frozen source and this test-owned PostgreSQL. It is NOT evidence of a customer
incident, the cause of the hosted SQLite lock failure, or universal concurrency
safety. Python here is 3.13.5, not hosted CI's 3.12; no full suite/hosted run,
Alembic migration validation, device acceptance, or multi-node load claim.

The controller has separately approved a minimal task-before-lease reorder in
claim, preserving all gates and REMOTE conflict precedence. That production fix
must start on `agent/sol-pg-lock-order-fix-20260929` FROM this immutable red
reproduction commit, not be folded into this branch/snapshot.
