# CONTROL-LOCK-ORDER: amended three-method delivery

Date: 2026-09-29. Work item: CONTROL-LOCK-ORDER.

- Integrated production ancestor: `831ada1077ce262db7e1546f1b8569995fed8431`.
- Immutable red reproduction: `4c1677fd0556af7662834b304b2393fa91940753`.
- Worktree baseline / parent: `937a349771d6503c8d606929da04cbcf95b14d57`.
- Branch: `agent/sol-control-lock-order-fix-20260929`.
- Reused worktree: `sol-ime-picker-20260929`; no checkout was created or renamed.
- The controller explicitly stopped the previous writer and transferred sole
  write ownership before these additions and test executions.
- This document supersedes the delivery status, NOT the historical contents,
  of `SUMMARY.md`. That file and all earlier red evidence are preserved.
- The delivery commit is the commit adding this document; its exact SHA is
  reported in the chat handoff (not embedded recursively in this file).

## Frozen amended contract and implementation

Production scope is exactly `PlatformTaskService.cancel`,
`PlatformTaskService.resume`, and `FleetLiveService.take_control`.
The already-applied three-method implementation was retained, not rewritten.
`scope-ast.log` confirms AST outside these three method bodies equals HEAD.

1. Cancel and resume probe task identity without a lock, reject foreign tenant,
   lock the identified Device, lock Task with `populate_existing=True`, and
   recheck tenant/device identity before original guards or mutations.
2. Take-control authenticates, locks Device, and deterministically locks task
   IDs in sorted order for business RUNNING OR runner CLAIMED/RUNNING before
   sweep/open/REMOTE replay/tier/consent. These prelocks do not mutate business
   state. The original device assertion remains after consent.
3. Lease lock and foreign-REMOTE rejection still precede the original
   business-RUNNING-only UPDATE, fencing increment and live changes.
4. No retry, timeout/pool change, schema, global lock rewrite, type-ignore
   change, security relaxation, task ledger or configuration edit.

The fixture remains real, test-owned loopback PostgreSQL, independent ASGI
applications/connections, natural API state transitions, event barriers and
PostgreSQL wait-edge observation. Local account metadata/fault injection occurs
only inside that disposable test database, never against external accounts.

## Review of the prior candidate

Confirmed defects, not conjectures about a model:

- The approved two-method design introduced Device -> Task ordering while
  reachable resume retained Task -> Device. Two real 40P01 errors are recorded
  in `resume-inversion-red.log`.
- Prelocking after sweep left a lease-before-task path on stale REMOTE sweep.
  `stale-remote-red.log` records one real 40P01 failure.
- Initial two-case and 13-case green runs did not cover those reachable
  interactions. They were insufficient to establish candidate readiness.

The first two-method design was controller-approved. Its omission is not
solely the prior executor's responsibility. The old executor preserved red
evidence and stopped delivery; this record does not recast that as a knowingly
false green delivery. One bounded engineering failure supports no general
claim about GPT-5.6 intelligence or model capability decline.

## Regression coverage and deterministic expectations

The full control-lock file now has 31 passing cases, including:

- Original cancel/claim and takeover/heartbeat cycles.
- PREFLIGHT and RESUME_CHECK becoming RUNNING during heartbeat, unchanged
  RUNNING-only pause semantics, stale REMOTE sweep/heartbeat.
- Resume versus cancel and resume versus take-control. The scheduler now
  guarantees resume holds Device first: both HTTP responses must be 200.
  Cancel finishes CANCEL_REQUESTED with matching AUTO lease and one fence
  increment; takeover finishes RESUME_CHECK with REMOTE lease and two fence
  increments. The previous broad final-state alternatives were removed.
- Resume probe barrier followed by natural cancellation or another resume,
  late commit intent, device/tenant identity changes, task deletion, account
  binding removal or version change. Locked reread must reject with exact
  404/409, no SQL error and no further task/lease/counter/audit mutation.
- Resume permission/tenant/pageVerified/commit-intent rejections: exact
  403/404/422/409 with unchanged durable state and audits.
- Existing cancel locked-freshness, idempotency, foreign-REMOTE preservation,
  permissions, identity and commit-intent cases.
- Tier refusal (403) and missing consent (428) with real RUNNING tasks remain
  mutation-free; tier wins even when consent is absent.
- Hard-timeout sweep returns 410 but commits owned lease cancellation and one
  close audit, without changing task state or fencing. This explicitly tests
  `_transact` committing sweep effects on DomainError.

Task snapshots include payload/result/account/binding/resume count;
durable snapshots include fencing and control epoch. Concurrent schedules
check SQL errors, HTTP results, durable outcomes and connection/worker cleanup.
All three full focused runs report owned PostgreSQL stop/removal.

## Actual verification

All commands below ran from the assigned worktree. Main's existing interpreter
and dependencies were reused without installation. No network CI work, phone,
deployment, binding/tenant/key operation outside disposable fixtures, business
send/upload/publish, or push was performed.

| Command / evidence | Exit | Result |
| --- | --- | --- |
| Full control-lock, `amended-full.log` | 0 | 31 passed, 16.67s |
| Tightened deterministic assertions, `amended-full-final.log` | 0 | 31 passed, 17.44s |
| Final RUNNING-task rejection guards, `amended-full-delivery.log` | 0 | 31 passed, 17.56s |
| Seven existing related suites, `related-integration.log` | 0 | 166 passed, 39.67s |
| Scoped Ruff, `ruff-check-final.log` | 0 | All checks passed |
| Scoped format, `ruff-format-final.log` | 0 | 3 files already formatted |
| Scoped mypy with MYPYPATH, `mypy.log` | 1 | Existing fleet_live.py:47 unused-ignore under changed discovery |
| Scoped raw mypy, `mypy-raw.log` | 0 | 2 source files clean |
| Configured package mypy, `mypy-configured.log` | 0 | 162 source files clean |
| Initial scoped Pyright, `pyright.log` | 0 | 0 errors; missing worktree .venv diagnostic |
| Invalid combined Pyright options, `pyright-final.log` | 4 | pythonpath cannot be combined with venvpath |
| Corrected configured Pyright, `pyright-configured.log` | 0 | 0 errors/warnings/informations |
| Corrected test Pyright, `pyright-test.log` | 0 | 0 errors/warnings/informations |
| Security boundaries, `security.log` | 0 | Passed |
| AST method-scope check, `scope-ast.log` | 0 | Only approved method bodies differ |
| `git diff --check` | 0 | Clean |

Failed invocations are preserved, not hidden by production/config changes.
Three Pyright logs had only their final blank line removed after staged
whitespace checking; all diagnostic text, including version notices, remains.
Mypy source discovery for the configured run uses explicit worktree
`PYTHONPATH`, not `MYPYPATH`. `source-resolution.log` records all ten configured
package locations under this worktree and Python 3.13.5. Pyright uses this
worktree's configuration/source paths and main's venv. These are local
worktree checks, not claims that main raw gates or hosted Python 3.12 CI were
rerun here. The parent owns integrated main full pytest and live CI.

### Exact commands

`P=../cloudctl-source/.venv/bin/python` and
`V=../cloudctl-source/.venv/bin` below are path abbreviations only.
Each log is stdout/stderr redirected under this evidence directory.

```bash
$P -m pytest -q -s -p no:cacheprovider \
  -W error::RuntimeWarning -W error::ResourceWarning \
  -W error::pytest.PytestUnraisableExceptionWarning \
  tests/integration/test_fleet_control_lock_order.py

$P -m pytest -q -rs -p no:cacheprovider \
  -W error::RuntimeWarning -W error::ResourceWarning \
  -W error::pytest.PytestUnraisableExceptionWarning \
  tests/integration/test_mobile_lock_order.py \
  tests/integration/test_fleet_live_session.py \
  tests/integration/test_fleet_live_transport.py \
  tests/integration/test_platform_tasks.py \
  tests/integration/test_mobile_task_api.py \
  tests/integration/test_fleet_cancel_reconcile.py \
  tests/integration/test_fleet_claim_recovery.py

$V/ruff check services/control-api/src/cloudctl_api/platform_tasks.py \
  services/control-api/src/cloudctl_api/fleet_live.py \
  tests/integration/test_fleet_control_lock_order.py
$V/ruff format --check services/control-api/src/cloudctl_api/platform_tasks.py \
  services/control-api/src/cloudctl_api/fleet_live.py \
  tests/integration/test_fleet_control_lock_order.py

env -u MYPYPATH -u PYTHONPATH $V/mypy --no-incremental --cache-dir=/dev/null \
  services/control-api/src/cloudctl_api/platform_tasks.py \
  services/control-api/src/cloudctl_api/fleet_live.py

env -u MYPYPATH \
  PYTHONPATH="$PWD/packages/domain/src:$PWD/packages/edge-protocol/src:$PWD/packages/lamda-driver/src:$PWD/packages/automation-sdk/src:$PWD/packages/observability/src:$PWD/services/control-api/src:$PWD/services/temporal-worker/src:$PWD/services/edge-hub/src:$PWD/services/outbox-dispatcher/src:$PWD/edge/gateway/src" \
  $P -m mypy --no-incremental --cache-dir=/dev/null

$V/pyright --venvpath ../cloudctl-source
$V/pyright --venvpath ../cloudctl-source \
  tests/integration/test_fleet_control_lock_order.py
bash scripts/check-security-boundaries.sh
git diff --check
```

Failed/diagnostic commands, retained verbatim in meaning:

```bash
env MYPYPATH=services/control-api/src:packages/domain/src:packages/edge-protocol/src:packages/lamda-driver/src:packages/automation-sdk/src:packages/observability/src:services/temporal-worker/src:services/edge-hub/src:services/outbox-dispatcher/src:edge/gateway/src \
  $P -m mypy --no-incremental \
  services/control-api/src/cloudctl_api/platform_tasks.py \
  services/control-api/src/cloudctl_api/fleet_live.py

$V/pyright --pythonpath ../cloudctl-source/.venv/bin/python \
  services/control-api/src/cloudctl_api/platform_tasks.py \
  services/control-api/src/cloudctl_api/fleet_live.py \
  tests/integration/test_fleet_control_lock_order.py

$V/pyright --venvpath ../cloudctl-source \
  --pythonpath ../cloudctl-source/.venv/bin/python \
  services/control-api/src/cloudctl_api/platform_tasks.py \
  services/control-api/src/cloudctl_api/fleet_live.py \
  tests/integration/test_fleet_control_lock_order.py
```

## Preserved historical hashes

SHA256:

```text
06fba6b0bf05c6e375d45a35218680995d34cc460f9612d85ce4af66a443e41f  SUMMARY.md
7e1e286f17403c83b17a2e559e055a0d7d8b134c07c1c8bff96718dbda554a89  blocked-candidate-production.patch
a1b345c24546359ed982aaf4f513cdda37040b465da4773b5ffe740f449c8064  resume-inversion-red.log
b90117beef90722e2d3f0c419ba541b545be04bc2099431278e79a9bcb14a91f  stale-remote-red.log
```

## Limits and parent handoff

- Earlier locking changes invalid-request waiting/error precedence; this is the
  explicitly acknowledged bounded behavior difference.
- The superset is locking-only. RESUME_CHECK/PREFLIGHT/QUEUED are not newly
  paused. Existing resume lease replacement semantics remain unchanged.
- Guard tests validate account binding observed at the existing validation
  point, not a new serialization contract for arbitrary concurrent binding
  changes.
- These schedules are strong regression evidence for the identified cycles,
  not a proof of global deadlock freedom or hardware/production acceptance.
- No remaining local source blocker was found in the approved scope. Parent
  must independently review, integrate and run main gates before pushing.
  No main full suite or remote CI result is claimed by this child.
- Unrelated untracked `artifacts/ime-picker-recovery-20260929/` and
  `artifacts/publish-permissions-20260929/` remain untouched and excluded.
- Commit scope: the two named production files, the control-lock test file,
  and only `artifacts/control-lock-order-20260929/fix/` evidence. No other
  production changes or resource locks are requested.
