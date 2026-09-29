# atomic-publish-dispatch-20260929

Date: 2026-09-29

## Identity

- Work item: `atomic-publish-dispatch-20260929`
- Branch: `agent/sol-atomic-dispatch-20260929`
- Frozen baseline: `7ee8424043f3f67e73f5284b4e4ff6a595a7ff8c`
- Model/effort requested: `gpt-5.6-sol/high`
- Evidence owner: this worker owns only this summary; the controller owns the final evidence index and `controller-review.md`.

## Owned Files

- `services/control-api/src/cloudctl_api/xianyu_publish.py`
- `services/control-api/src/cloudctl_api/platform_tasks.py`
- `services/control-api/src/cloudctl_api/mobile_service.py`
- `tests/integration/test_xianyu_publish_dispatch.py`
- `artifacts/atomic-publish-dispatch-20260929/SUMMARY.md`

Pre-existing untracked directories were preserved and not staged:

- `artifacts/ime-picker-recovery-20260929/`
- `artifacts/publish-permissions-20260929/`

No task plan, schema, migration, OpenAPI, Android, Web, CI, or controller evidence file was changed.

## Implementation

- Xianyu queue dispatch now passes its caller-owned `AsyncSession` through platform-task creation.
- `MobileTaskService._insert_task` keeps the existing self-owned unit-of-work entry point and adds a session-bound path that validates, locks, inserts, and explicitly flushes without committing or rolling back the caller transaction.
- The initial idempotency lookup always runs before taking the device row lock, preserving ordinary direct replay's lock-free return of an existing task. A second lookup after the device lock is enabled only for caller-owned sessions and the pre-existing order-collection path.
- `PlatformTaskService.create` propagates the supplied session through publish-listing freeze reads, mobile-task insertion, business-field/snapshot stamping, and task-view reads. Existing callers that do not supply a session retain their self-owned unit-of-work behavior.
- Queue row locks, task insertion, command/snapshot stamping, canonical `completionBoundary` hash, target `IN_FLIGHT` linkage, task ID append, and dispatch audit now commit or roll back in one SQL transaction.
- A caller-owned database `IntegrityError` is translated at the queue owner boundary to the existing `task idempotency conflict` API response. The failed session is not queried, committed, rolled back internally, or replaced with a recovery transaction; the outer unit of work performs the rollback.
- Existing legacy orphan recovery remains identity-validated. Recovered tasks are linked without changing business state, control mode, result, command payload, or snapshot hash.
- No automatic confirm or publish action was added. The recipe remains open-only and stops at the human commit boundary.

## Frozen-Baseline Red Proof

The current regression nodes were run against a read-only temporary `git archive` of the exact frozen baseline while the test file came from this worktree:

```sh
BASE=$(mktemp -d /tmp/atomic-dispatch-baseline.XXXXXX)
git archive 7ee8424043f3f67e73f5284b4e4ff6a595a7ff8c | tar -x -C "$BASE"
PYTHONPATH="$BASE/packages/domain/src:$BASE/packages/edge-protocol/src:$BASE/packages/lamda-driver/src:$BASE/packages/automation-sdk/src:$BASE/packages/observability/src:$BASE/services/control-api/src:$BASE/services/temporal-worker/src:$BASE/services/edge-hub/src:$BASE/services/outbox-dispatcher/src:$BASE/edge/gateway/src" \
  /Users/wangziheng/Desktop/01-主战场/LAMDA云控系统/cloudctl-source/.venv/bin/python \
  -m pytest -c /dev/null --asyncio-mode=auto -p no:cacheprovider -q \
  "$PWD/tests/integration/test_xianyu_publish_dispatch.py::test_postgres_task_is_not_visible_or_claimable_before_queue_commit" \
  "$PWD/tests/integration/test_xianyu_publish_dispatch.py::test_postgres_dispatch_failure_rolls_back_task_link_and_audit[after_insert]"
```

Result: exit `1`, `2 failed in 2.27s`.

- Before queue commit, the second application/connection observed task count `1` instead of `0`, and Companion claim returned `200`.
- After an injected failure immediately following task insertion, the queue target rolled back to `PENDING` but one unlinked task survived.

This reproduces the documented non-atomic orphan window on the exact baseline.

## PostgreSQL Atomicity Evidence

All atomicity tests start a disposable real local PostgreSQL cluster. The two API applications use separate engines and connection pools.

Focused pre-commit and rollback proof:

```sh
$PYTHON -m pytest -q tests/integration/test_xianyu_publish_dispatch.py \
  -k 'postgres_task_is_not_visible_or_claimable_before_queue_commit or postgres_dispatch_failure_rolls_back_task_link_and_audit'
```

Result: exit `0`, `4 passed, 12 deselected in 3.32s`.

- A second connection sees zero task rows before commit.
- A second application's claim cannot cross the uncommitted queue transaction; after commit it receives the same fully frozen task returned by dispatch.
- Injected failures after task insert, snapshot stamping, and target/audit mutation each leave zero new tasks, zero linkage, and zero dispatch audits.

Real database constraint failure mapping:

```sh
$PYTHON -m pytest -q \
  tests/integration/test_xianyu_publish_dispatch.py::test_postgres_caller_owned_flush_integrity_error_maps_to_conflict_and_rolls_back
```

Result: exit `0`, `1 passed in 1.62s`.

The test forces PostgreSQL to reject a caller-owned session flush. The API returns `409 task idempotency conflict`; the outer transaction leaves the target `PENDING` with no task, link, or audit.

Complete dispatch file:

```sh
$PYTHON -m pytest -q tests/integration/test_xianyu_publish_dispatch.py
```

Result after the direct-replay follow-up: exit `0`, `18 passed in 8.88s`.

Coverage includes:

- text-only and media task creation;
- canonical snapshot hash includes `completionBoundary` and excludes the prior `snapshotSha256` value from the hash input;
- exactly one fully frozen linked task and one audit after commit;
- concurrent same-target and different-target dispatch remains serial across separate API apps;
- a lost HTTP response after commit does not mint a second task;
- an explicitly constructed legacy paused orphan is recovered without changing state, control mode, result, payload, or hash;
- partial or mismatching orphan identity still fails closed;
- direct platform-task idempotent replay still preserves a started task;
- ordinary direct platform-task replay returns the existing paused task while a separate PostgreSQL transaction holds the device row lock, without waiting for that lock or mutating task state;
- no automatic success confirmation or publish-button step is introduced.

### Direct Replay Lock Follow-up

Review of commit `4d687c36d3e680c96260202524e032d6342add09` found that the conditional was attached to the first idempotency lookup instead of the second lookup after the device lock.

Red proof before the correction:

```sh
$PYTHON -m pytest -q \
  tests/integration/test_xianyu_publish_dispatch.py::test_postgres_direct_platform_replay_does_not_wait_for_device_lock
```

Result: exit `1`, `1 failed in 1.65s`; replay did not complete during the positive completion window and returned only after the held `DeviceRow FOR UPDATE` lock was released.

After moving the condition to the second lookup and using a 2-second positive completion window while retaining the device lock:

```sh
$PYTHON -m pytest -q \
  tests/integration/test_xianyu_publish_dispatch.py::test_postgres_direct_platform_replay_does_not_wait_for_device_lock
```

Result: exit `0`, `1 passed in 1.38s`. The replay returned the original task and preserved `PAUSED_WAITING_USER`, `REMOTE`, result, command payload, and snapshot hash.

## Broad Regression

All commands used the main virtual environment and explicit source paths for this checkout:

```sh
PYTHON=/Users/wangziheng/Desktop/01-主战场/LAMDA云控系统/cloudctl-source/.venv/bin/python
export PYTHONPATH="$PWD/packages/domain/src:$PWD/packages/edge-protocol/src:$PWD/packages/lamda-driver/src:$PWD/packages/automation-sdk/src:$PWD/packages/observability/src:$PWD/services/control-api/src:$PWD/services/temporal-worker/src:$PWD/services/edge-hub/src:$PWD/services/outbox-dispatcher/src:$PWD/edge/gateway/src"
```

```sh
$PYTHON -m pytest -q \
  tests/integration/test_xianyu_publish_dispatch.py \
  tests/integration/test_xianyu_publish_permissions.py \
  tests/unit/test_xianyu_publish_recipe.py \
  tests/integration/test_xianyu_publish_delta.py \
  tests/integration/test_publish_commands.py \
  tests/integration/test_platform_tasks.py \
  tests/integration/test_mobile_task_api.py \
  tests/integration/test_task_schedules.py \
  tests/integration/test_xhs_publish_delta.py \
  tests/integration/test_douyin_publish_delta.py \
  tests/integration/test_xianyu_maintenance.py \
  tests/integration/test_orders_sync.py \
  tests/integration/test_order_delivery.py
```

Final result after the direct-replay lock correction: exit `0`, `244 passed, 1 skipped in 58.19s`.

The skip is the existing SQLite-only guard at `tests/integration/test_order_delivery.py:385`: `row-lock concurrency requires PostgreSQL`. The new atomic dispatch suite supplies the required real-PostgreSQL concurrency proof.

The controller-requested shared-call-site subset was also run with skip reasons enabled:

```sh
$PYTHON -m pytest -q -rs \
  tests/integration/test_xianyu_maintenance.py \
  tests/integration/test_orders_sync.py \
  tests/integration/test_order_delivery.py
```

Result: exit `0`, `134 passed, 1 skipped in 34.39s`, with the same explicit PostgreSQL-only skip above.

The follow-up direct/mobile/order impact set was also rerun:

```sh
$PYTHON -m pytest -q -rs \
  tests/integration/test_platform_tasks.py \
  tests/integration/test_mobile_task_api.py \
  tests/integration/test_publish_commands.py \
  tests/integration/test_task_schedules.py \
  tests/integration/test_xianyu_maintenance.py \
  tests/integration/test_orders_sync.py \
  tests/integration/test_order_delivery.py
```

Result: exit `0`, `199 passed, 1 skipped in 45.83s`, with the same explicit PostgreSQL-only skip above.

## Static Verification

```sh
$PYTHON -m ruff format \
  services/control-api/src/cloudctl_api/mobile_service.py \
  services/control-api/src/cloudctl_api/platform_tasks.py \
  services/control-api/src/cloudctl_api/xianyu_publish.py \
  tests/integration/test_xianyu_publish_dispatch.py
$PYTHON -m ruff check \
  services/control-api/src/cloudctl_api/mobile_service.py \
  services/control-api/src/cloudctl_api/platform_tasks.py \
  services/control-api/src/cloudctl_api/xianyu_publish.py \
  tests/integration/test_xianyu_publish_dispatch.py
$PYTHON -m mypy \
  services/control-api/src/cloudctl_api/mobile_service.py \
  services/control-api/src/cloudctl_api/platform_tasks.py \
  services/control-api/src/cloudctl_api/xianyu_publish.py
git diff --check
```

Result: exit `0`; Ruff reports all checks passed, mypy reports `Success: no issues found in 3 source files`, and `git diff --check` is clean.

This is scoped worktree verification using the main `.venv` with the explicit `PYTHONPATH` shown above. It does not claim equivalence to raw CI mypy import treatment on the controller's integrated main; the controller will rerun those raw gates after cherry-pick.

## Residual Limits

- Legacy orphan recovery remains only for tasks created by older non-atomic code or explicitly constructed compatibility cases. New queue dispatch cannot commit a task without its target linkage and audit.
- A client that loses the HTTP response after a successful commit receives the existing `409` on direct retry and must reconcile through queue/task GET; no duplicate task is minted.
- Atomicity is proven locally with disposable PostgreSQL and separate application connections. No production database, external HTTP service, device, ADB, install, deploy, upload, account rebind, real send, or real publish was used.
- No hardware or production acceptance claim is made.
