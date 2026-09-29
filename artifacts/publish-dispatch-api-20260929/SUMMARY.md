# publish-dispatch-api-20260929

Date: 2026-09-29

## Identity

- Work item: `publish-dispatch-api-20260929`
- Branch: `agent/sol-publish-dispatch-api-20260929`
- Frozen baseline: `933964b2ded8a22f0d3c74d8bb061a0098b2266b`
- Implementation commit: `f058b9d41a7c3ae29b23b559329788ba22e3459c`
- Model/effort requested: `gpt-5.6-sol/high`

## Files

Implementation commit:

- `services/control-api/src/cloudctl_api/xianyu_publish.py`
- `tests/integration/test_xianyu_publish_dispatch.py`

Evidence commit adds only:

- `artifacts/publish-dispatch-api-20260929/SUMMARY.md`

Pre-existing untracked directories `artifacts/ime-picker-recovery-20260929/` and
`artifacts/publish-permissions-20260929/` were preserved and not staged.

## Change

- Dispatch locks every target row in the tenant queue with PostgreSQL
  `SELECT ... ORDER BY position FOR UPDATE`.
- The authoritative mint boundary now rechecks all three conditions while that
  database lock is held: the requested target is dispatchable, no target is
  `IN_FLIGHT`, and the requested target is the first eligible position.
- The queue lock remains held across `PlatformTaskService.create`, task snapshot
  completion-boundary stamping, target transition to `IN_FLIGHT`, task ID append,
  and dispatch audit insertion.
- Existing response fields, permissions, tenant scoping, open-only recipe,
  target/task/result identity, and terminal-target rejection remain unchanged.
- No schema, migration, OpenAPI, client, Android, task-plan, or other production
  module was changed.

## Regression Evidence

Normal verification commands used this exact shell setup:

```sh
cd '/Users/wangziheng/Desktop/01-主战场/LAMDA云控系统/sol-ime-picker-20260929'
PYTHON='/Users/wangziheng/Desktop/01-主战场/LAMDA云控系统/cloudctl-source/.venv/bin/python'
export PYTHONPATH="$PWD/packages/domain/src:$PWD/packages/edge-protocol/src:$PWD/packages/lamda-driver/src:$PWD/packages/automation-sdk/src:$PWD/packages/observability/src:$PWD/services/control-api/src:$PWD/services/temporal-worker/src:$PWD/services/edge-hub/src:$PWD/services/outbox-dispatcher/src:$PWD/edge/gateway/src"
```

### Frozen-baseline red proof

The exact controller sequence was run with every source path pointed at main
checkout `933964b`, while using the new test node from this worktree:

```sh
PYTHONPATH="/Users/wangziheng/Desktop/01-主战场/LAMDA云控系统/cloudctl-source/packages/domain/src:/Users/wangziheng/Desktop/01-主战场/LAMDA云控系统/cloudctl-source/packages/edge-protocol/src:/Users/wangziheng/Desktop/01-主战场/LAMDA云控系统/cloudctl-source/packages/lamda-driver/src:/Users/wangziheng/Desktop/01-主战场/LAMDA云控系统/cloudctl-source/packages/automation-sdk/src:/Users/wangziheng/Desktop/01-主战场/LAMDA云控系统/cloudctl-source/packages/observability/src:/Users/wangziheng/Desktop/01-主战场/LAMDA云控系统/cloudctl-source/services/control-api/src:/Users/wangziheng/Desktop/01-主战场/LAMDA云控系统/cloudctl-source/services/temporal-worker/src:/Users/wangziheng/Desktop/01-主战场/LAMDA云控系统/cloudctl-source/services/edge-hub/src:/Users/wangziheng/Desktop/01-主战场/LAMDA云控系统/cloudctl-source/services/outbox-dispatcher/src:/Users/wangziheng/Desktop/01-主战场/LAMDA云控系统/cloudctl-source/edge/gateway/src" \
  /Users/wangziheng/Desktop/01-主战场/LAMDA云控系统/cloudctl-source/.venv/bin/pytest \
  -c /dev/null --asyncio-mode=auto -p no:cacheprovider -q \
  /Users/wangziheng/Desktop/01-主战场/LAMDA云控系统/sol-ime-picker-20260929/tests/integration/test_xianyu_publish_dispatch.py::test_direct_dispatch_cannot_bypass_in_flight_after_next_returns_empty
```

Result: exit `1`, `1 failed`. Runtime sequence: first target dispatch `200`,
`POST .../next` `204`, direct second target dispatch incorrectly `200` instead
of expected `409`.

### Fixed dispatch regressions

```sh
$PYTHON -m pytest -q tests/integration/test_xianyu_publish_dispatch.py
```

Result: exit `0`, `6 passed in 2.98s`.

Coverage includes:

- direct first-position skip rejection;
- exact reproduced IN_FLIGHT bypass sequence;
- concurrent same-target dispatch through two API apps and independent
  PostgreSQL engines/connection pools;
- concurrent different-target dispatch under the same queue lock;
- task commit followed by queue-transaction failure, then same-key recovery
  without duplicate task or ghost `IN_FLIGHT` state;
- queue dispatch -> authenticated Companion claim -> pause event -> platform task
  `PAUSED_WAITING_USER`, with matching queue/target identity, queue still
  `IN_FLIGHT`, open-only steps, and zero success-confirm audit events.

The concurrency fixture starts a disposable local PostgreSQL cluster. It does
not use an in-process mutex and SQLite is not cited as lock evidence. The two API
apps run in one pytest process, but use separate application instances, engines,
and connection pools; the blocking behavior is therefore provided by PostgreSQL
row locking and applies across API processes using the same database.

### Requested existing suites

```sh
$PYTHON -m pytest -q \
  tests/integration/test_xianyu_publish_dispatch.py \
  tests/integration/test_xianyu_publish_permissions.py \
  tests/unit/test_xianyu_publish_recipe.py \
  tests/integration/test_xianyu_publish_delta.py \
  tests/integration/test_publish_commands.py \
  tests/integration/test_platform_tasks.py
```

Result: exit `0`, `61 passed in 25.03s`.

This includes the existing queue replay and permission coverage.

### Static checks

```sh
/Users/wangziheng/Desktop/01-主战场/LAMDA云控系统/cloudctl-source/.venv/bin/ruff check \
  services/control-api/src/cloudctl_api/xianyu_publish.py \
  tests/integration/test_xianyu_publish_dispatch.py
```

Result: exit `0`, `All checks passed!`.

```sh
$PYTHON -m mypy services/control-api/src/cloudctl_api/xianyu_publish.py
```

Result: exit `0`, `Success: no issues found in 1 source file`.

```sh
git diff --check
```

Result: exit `0`.

## Residual Limits

- Without a schema/outbox change, task creation and queue-target commit are not
  one atomic database transaction: `PlatformTaskService.create` commits its task
  separately while the queue transaction holds its row locks.
- If the API process terminates after the task commit but before the queue commit,
  the queue remains `PENDING` and the already-created task can temporarily exist
  without its target linkage; it may be claimable. Retrying dispatch uses the
  unchanged attempt number and stable dispatch key, reuses that task, and commits
  the linkage without duplication. No automatic orphan reconciliation was added.
- A repeated request after the queue commit sees `IN_FLIGHT` and returns `409`, as
  allowed by the frozen contract; clients reconcile through queue/task GET.
- No physical device, ADB, production API/network, deployment, upload, account
  rebind, real send, or real publish was used. No success confirmation was
  invented, and a paused task was not promoted to publication success.
