# PG-LOCK-ORDER Minimal Fix

Status: approved-scope fix verified locally; full combined integration remains
the controller's responsibility. No push, deployment, device or customer claim.

- Frozen production baseline: `7d58f6b28158292722c7d037998163f5fcbfca89`.
- Immutable RED / UNMERGEABLE reproduction commit:
  `2140f6954ed51c47c08949b6935e27ec722b7d61` on
  `agent/sol-pg-lock-order-repro-20260929`.
- Fix branch: `agent/sol-pg-lock-order-fix-20260929`, based directly on that
  reproduction commit. The fix is the commit containing this document.
- Writes: `services/control-api/src/cloudctl_api/mobile_service.py`,
  `tests/integration/test_mobile_lock_order.py`, new evidence in this directory.
  No existing baseline evidence was changed.

## Production Delta

Only `MobileTaskService.claim` is changed: 10 existing lines moved, no changed
expressions or new production logic. At `mobile_service.py:1521`, active
MobileTask SELECT FOR UPDATE now precedes DeviceLease acquisition (`:1531`).
The existing REMOTE ConflictError still precedes the valid-active-task return
(`:1540`). Initial Device lock (`:1474`), all earlier checks, expired-task
recovery, queue selection, account mutex, lease/fencing and authorization
semantics retain their original statements.

`fix-source-check.json` records an AST comparison against the repro commit:
after the single approved permutation of active-task select / lease get / REMOTE
guard, the complete old module AST equals the new module AST. This proves the
scope of the change, not semantic equivalence of the changed lock order.

Actual tested SHA256:

- Production module:
  `b2e5face24d05885bd444be05010c7f8194ffbc14a63e10235c975bd3bcea2d1`.
- Final test file:
  `fa8f8f54973d91ae4ab27229664d94fd0786342f88ab7601602f0302f7636724`.
- Unchanged baseline production module:
  `b026eba59dc3a8bcbd01302eb439c4c00898849c19b6743d8afb7dde21416d1c`.

## Red to Green

The immutable baseline had **9 passed / 4 failed**, exit 1. All four failures
were actual PostgreSQL SQLSTATE `40P01`, covering finish and heartbeat against
claim in both PREFLIGHT and RUNNING. This is reproduced test behavior, not a
customer incident or proof of the hosted SQLite failure's cause.

The fixed standalone run has **11 passed / 0 failed / 0 skipped**, exit 0,
6.34 s. The same four desired cases now return claim HTTP 204 and runner HTTP 200
without SQLSTATE errors. Actual lock snapshots show claim has Device, but not
DeviceLease, when it first requests the active task lock. The runner holds the
task, is released at that request, commits its task/lease update, and lets claim
continue. `fix.log` preserves actual queries/PIDs/outcomes and durable states;
`fix-postgres.log` has no `40P01` report.

The continuing test deliberately:

- Removes only the four historical cases that expected BAD behavior. Their exact
  unchanged source and logs remain on the immutable repro commit; the permanent
  test suite must not require a deadlock after it has been fixed.
- Retains all four strict desired HTTP/outcome assertions, four sequential
  controls, cancellation/draining and final durable task/lease/fencing checks.
- Observes the first real claim task-lock request, not successful acquisition
  of both inverted locks. The request snapshot is latched so a later queued-task
  SELECT does not overwrite the active-task observation.
- Adds two normal-API REMOTE controls (`test_mobile_lock_order.py:550`):
  active PREFLIGHT still returns the exact REMOTE conflict (409) rather than
  early 204; a RUNNING task paused by real test-local take-control still returns
  204 through the earlier blocking-state guard. No database state is hand-edited
  to produce either case.

Success states retain exactly one task/lease, original attempt and fencing,
matching tenant/device identities, terminal result plus lease cancellation for
finish, and matching task/lease expiry plus updated step for heartbeat. Every
probe drains both workers, leaves zero pool checkouts, and verifies zero other
open transactions/lock waiters using the test-owned database's pg_stat_activity.

## Focused Regressions

Final combined focused run: **183 passed / 3 skipped / 0 failures / 0 errors**,
exit **0**, 54.91 s. This includes the new 11 cases and **172 passing existing
cases**, with existing test modules unchanged.

| Module under tests/integration | Passed | Skipped |
| --- | ---: | ---: |
| test_mobile_lock_order.py | 11 | 0 |
| test_mobile_task_api.py | 28 | 0 |
| test_platform_tasks.py | 25 | 0 |
| test_fleet_claim_recovery.py | 11 | 0 |
| test_fleet_identity.py | 18 | 0 |
| test_fleet_cancel_reconcile.py | 47 | 0 |
| test_control_plane_hotfix.py | 12 | 0 |
| test_fleet_two_devices.py | 11 | 3 |
| test_fleet_live_session.py | 20 | 0 |

The three skips are unchanged hardware-only Q10 placeholders, not PostgreSQL
discovery failures or newly added skips:

- `test_fleet_two_devices.py:1168`: physical partition after gated intent.
- `test_fleet_two_devices.py:1177`: on-device DeviceArbiter single-writer proof.
- `test_fleet_two_devices.py:1186`: real accessibility/IME/unlock gates.

Exact reasons are retained in `focused.log` and `focused-junit.xml`; per-module
counts and four race results are parsed into `fix-results.json`. No hardware
test was executed or converted to a software acceptance claim.

## Commands and Gates

All commands ran in:
`/Users/wangziheng/Desktop/01-主战场/LAMDA云控系统/sol-publish-queue-20260929`.
For the literal invocations below, `VENV` is
`/Users/wangziheng/Desktop/01-主战场/LAMDA云控系统/cloudctl-source/.venv`.

```sh
env -i PATH="$PATH" HOME="$HOME" TMPDIR="${TMPDIR:-/tmp}" LANG=C LC_ALL=C \
  PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH="$PWD/services/control-api/src:$PWD/packages/domain/src:$PWD/packages/observability/src:$PWD/packages/edge-protocol/src" \
  "$VENV/bin/python" -m pytest -p no:cacheprovider -q -s \
  tests/integration/test_mobile_lock_order.py \
  --junitxml=artifacts/pg-lock-order-20260929/fix-junit.xml \
  > artifacts/pg-lock-order-20260929/fix.log 2>&1
# exit 0: 11 passed; 6.34 s

env -i PATH="$PATH" HOME="$HOME" TMPDIR="${TMPDIR:-/tmp}" LANG=C LC_ALL=C \
  PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH="$PWD/services/control-api/src:$PWD/packages/domain/src:$PWD/packages/observability/src:$PWD/packages/edge-protocol/src" \
  "$VENV/bin/python" -m pytest -p no:cacheprovider -q -rs \
  tests/integration/test_mobile_lock_order.py \
  tests/integration/test_mobile_task_api.py \
  tests/integration/test_platform_tasks.py \
  tests/integration/test_fleet_claim_recovery.py \
  tests/integration/test_fleet_identity.py \
  tests/integration/test_fleet_cancel_reconcile.py \
  tests/integration/test_control_plane_hotfix.py \
  tests/integration/test_fleet_two_devices.py \
  tests/integration/test_fleet_live_session.py \
  --junitxml=artifacts/pg-lock-order-20260929/focused-junit.xml \
  > artifacts/pg-lock-order-20260929/focused.log 2>&1
# exit 0: 183 passed, 3 existing hardware skips; 54.91 s

"$VENV/bin/ruff" format --check .
# exit 0: 713 files already formatted; fix-ruff-format.log
"$VENV/bin/ruff" check .
# exit 0: All checks passed; fix-ruff-check.log
"$VENV/bin/pyright" \
  --venvpath /Users/wangziheng/Desktop/01-主战场/LAMDA云控系统/cloudctl-source
# exit 0: configured production sources, 0 errors/warnings; fix-pyright-production.log
"$VENV/bin/pyright" \
  --venvpath /Users/wangziheng/Desktop/01-主战场/LAMDA云控系统/cloudctl-source \
  tests/integration/test_mobile_lock_order.py
# exit 0: 0 errors/warnings; fix-pyright-test.log
env -u MYPYPATH -u PYTHONPATH "$VENV/bin/mypy" --no-incremental --cache-dir=/dev/null \
  services/control-api/src/cloudctl_api/mobile_service.py
# exit 0: no issues in 1 source file; fix-mypy.log
bash scripts/check-security-boundaries.sh
# exit 0: Security boundary checks passed; fix-security.log
git diff --check
# exit 0: fix source changes
git diff --cached --check -- services/control-api/src/cloudctl_api/mobile_service.py \
  tests/integration/test_mobile_lock_order.py artifacts/pg-lock-order-20260929/FIX.md
# exit 0: staged source and handoff document
```

This mypy invocation targets the actual changed worktree module; it is NOT the
full raw hosted mypy command. Pyright uses the local worktree's configured
sources with the main checkout's existing venv dependencies. No MYPYPATH override,
type ignore removal, py.typed/package/config change, dependency installation or
version bump. Python is local 3.13.5 rather than hosted CI 3.12; pinned
Ruff/Pyright remain 0.16.5/1.1.411.

The initial focused-format check found only formatting of the new request-snapshot
condition. Pinned Ruff formatted that test before the final 183/3 run; production
source and all test assertions were unchanged.

## Cleanup and Reporting Limits

The safe fixture bounds in `SUMMARY.md` remain in place: fresh loopback cluster,
per-test UUID database, cleared ambient connection settings, explicit DSN and
data-directory check, standard 1 s deadlock detector, test-only 10 s statement
limit, 20 s probe / 5 s drain bounds. No random sleeps, retries, pool tuning or
production timeout changes. Existing PG integration fixtures ran with an empty
environment except the explicitly supplied local tool/test paths.

Intentional cancellation still produces **two driver ERROR logs** containing
CancelledError in `fix.log`. They are not filtered or claimed to be silent
cleanup. Both request workers, zero pool checkouts, unchanged durable state and
zero remaining transactions/lock waiters are asserted; no `Event loop is closed`
appears. Client/lifespan/engine then close before the owned cluster is stopped.
The standalone owned data directory is:
`/private/var/folders/6b/g5wj9vms7b35lw_73jr6dk940000gn/T/pytest-of-wangziheng/pytest-104/mobile-lock-order-pg0/data`.
Its `pg_ctl -D <path> status` exits **3**, `no server running`; server shutdown
is preserved in `fix-postgres.log`.

Raw baseline PostgreSQL logs intentionally retain server-emitted trailing
whitespace. Their unrestricted repro staged whitespace check was exit 2,
separate from passing source/summary checks, as recorded in `SUMMARY.md`.
Those immutable raw logs were not reformatted, hidden by exclusions, or changed
by this fix. The fix's own source diff whitespace check passes.

Final whitespace-audit clarification: the verbatim
`pyright-verified.log:4` in the repro commit also has a new blank line at EOF,
so the repro summary's earlier "solely" PostgreSQL-log attribution was incomplete.
The unrestricted FIX staged check exits 2 for the same tool-emitted EOF blank
line in `fix-pyright-production.log:4` and `fix-pyright-test.log:4`. These are
raw-output formatting notices, not type or source diagnostics. The unchanged
red snapshot is preserved; this document records the correction explicitly.

No full combined suite, new hosted CI, deployment, device acceptance, customer
incident or global lock-order safety is claimed. The controller plans integration
with `9de94e9`; that combined state is NOT tested here. The controller separately
assigned queued-cancel/retained-lease and live-take-control/heartbeat hypotheses
to Kuhn; neither is investigated or changed by this production patch.

Integrate only the complete fixed branch state, not the intentionally failing
repro commit alone. The fix commit depends on its repro parent. Scope beyond
MobileTaskService.claim requires a separate handoff; all `tests/load/fleet/**`,
workflows, Android, migrations, task ledger and key configuration remain unchanged.
