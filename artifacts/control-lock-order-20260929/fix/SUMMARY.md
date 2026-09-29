# CONTROL-LOCK-ORDER FIX

- Integrated baseline: `831ada1077ce262db7e1546f1b8569995fed8431`.
- Immutable reproduction: `4c1677fd0556af7662834b304b2393fa91940753`, originally
  reproduced against `7d58f6b28158292722c7d037998163f5fcbfca89`.
- Merge preserving both ancestors: `937a349771d6503c8d606929da04cbcf95b14d57`.
- Branch: `agent/sol-control-lock-order-fix-20260929`.
- Authorized production changes: `PlatformTaskService.cancel` and
  `FleetLiveService.take_control` only.

The original reproduction summary, historical characterization and logs remain
unchanged. Combined-baseline red verification precedes any production edit.

## Status: blocked, not an integration candidate

The authorized two-method candidate resolves the original two cycles, but the
controller-requested bounded resume review exposed two real PostgreSQL deadlocks
on the candidate. Production work is paused pending an explicit revised
contract. `PlatformTaskService.resume` has NOT been edited.

The uncommitted production candidate is preserved exactly as
`blocked-candidate-production.patch`, relative to the merge above:
SHA256 `7e1e286f17403c83b17a2e559e055a0d7d8b134c07c1c8bff96718dbda554a89`.
It changes only `cancel` and `take_control`. No candidate production commit,
push, integration or broad lock-order redesign has been performed.

## Verification chronology

| Source / probe | Result | Exit | Evidence |
| --- | --- | --- | --- |
| Combined baseline, before production edits | 2 failed on 40P01, 15.51s | 1 | `combined-baseline-red.log` |
| Two-method candidate, original probes | 2 passed, 2.06s | 0 | `initial-green.log` |
| Candidate, original probes plus focused guards | 13 passed, 2 deselected, 9.04s | 0 | `focused-guards.log` |
| Candidate, new paused-resume probes | 2 failed on 40P01, 13 deselected, 4.68s | 1 | `resume-inversion-red.log` |

All four runs use the disposable loopback PostgreSQL fixture, natural ASGI
requests, default deadlock detector, independent connections, event barriers and
strict RuntimeWarning / ResourceWarning / PytestUnraisableExceptionWarning
filters. No retries, sleeps, skipped tests, xfails, pool changes or database
timeout changes were added.

The 13 passing cases cover:

- both original deadlock probes;
- CLAIMED/PREFLIGHT and RUNNING/RESUME_CHECK heartbeat transitions during
  take-control, ending in the unchanged RUNNING-only pause behavior;
- refreshed cancellation state after a concurrent natural RUNNING or SUCCEEDED
  transition;
- late legacy commit-intent, changed device/tenant identity and deleted-task
  fault cases, all fail-closed with no cancel audit or lease mutation;
- cancel permission/tenant denial, idempotent revision/audit behavior and
  preservation of a foreign REMOTE occupation;
- PREFLIGHT and QUEUED tasks remaining unpaused by take-control;
- conflicting REMOTE-owner rejection before task/lease/fencing mutation and
  idempotent REMOTE replay.

The injected identity/legacy-marker fault cases write only this test-owned
database. All normal state transitions and both resume reproductions use
natural APIs.

## Confirmed resume inversions

Both cases naturally create/enroll a simulated Companion, create and claim a
read-only task, heartbeat it to RUNNING, then invoke `:pause` and `:ack-paused`.
The precondition is therefore committed `PAUSED_WAITING_USER`, runner RUNNING,
an empty command payload (no commit intent), and a valid same-tenant task.
The resume request contains `pageVerified: true`.

For the live case, an authorized input-capable VIEWING session is established
before the task claim. No selector, permission or consent guard rejects it.

### Resume versus cancel

- resume PID **9898** acquires the task FOR UPDATE, then pauses at the barrier.
- cancel PID **9900** acquires the DeviceRow and waits for that task.
- Observer confirms `9900 -> 9898` on `Lock / transactionid`.
- Releasing resume lets it pass the genuine resume guards, then request the
  DeviceRow held by cancel.
- PostgreSQL reports **40P01**. cancel returns **500**, resume returns **200**.
- The task durably becomes RUNNING / RESUME_CHECK with a new matching AUTO
  lease and one resume epoch increment; cancellation does not partially apply.

### Resume versus live take-control

- resume PID **9916** acquires the task FOR UPDATE.
- take-control PID **9920** acquires the DeviceRow, then its new prelock SELECT
  includes the business-paused row because the runner status is RUNNING.
- Observer confirms `9920 -> 9916` on that task SELECT.
- resume next requests the DeviceRow, completing the reverse wait.
- PostgreSQL reports **40P01**. take-control returns **500**, resume returns
  **200**.
- The task durably becomes RUNNING / RESUME_CHECK with a matching AUTO lease.
  The failed takeover does not install a REMOTE lease.

Relevant current candidate locations:

- `platform_tasks.py:696`: cancel now locks DeviceRow before refreshed task.
- `platform_tasks.py:1047`: unchanged resume locks task, checks resume
  eligibility/page/commit-intent, then locks DeviceRow.
- `fleet_live.py:552`: take-control locks DeviceRow before the active-runner
  superset SELECT.
- `test_fleet_control_lock_order.py:867`: new parameterized desired regression.

These results confirm the reviewer's reachable-state concern on the current
candidate. They do not authorize changing resume or excluding paused rows from
the live superset. No alternative global lock contract has been implemented.

## Cleanup and scope

Both new red cases record zero remaining request workers and zero checked-out
connections before failing their desired no-SQL-error assertions. The fixture
then closes clients/lifespans/engines and stops/removes its own PostgreSQL
cluster. The 13-pass run also records successful teardown. A final process scan
found no `postgres.*control-lock-owned-pg` process.

The original immutable repro files compare identical to
`4c1677fd0556af7662834b304b2393fa91940753`. The two unrelated untracked evidence
directories remain untouched. No mobile-service, load-test, existing fixture,
workflow, task-ledger, schema, settings or device changes.

Ruff lint currently passes for the two owned production files and the new test
file. Ruff format requests only a one-line wrapping adjustment in cancel; it
has not been applied during the production hold. Scoped typing, the unchanged
11 active-lock-order cases and broader affected suites remain pending the
controller's revised design, rather than presenting this blocked candidate as
ready.

## Exact test commands

Run from the assigned worktree, using main's `.venv` and this checkout's source:

```bash
ROOT="$PWD"
PYTHON="$ROOT/../cloudctl-source/.venv/bin/python"
export PYTHONPATH="$ROOT/services/control-api/src:$ROOT/packages/domain/src:$ROOT/packages/edge-protocol/src:$ROOT/packages/lamda-driver/src:$ROOT/packages/automation-sdk/src:$ROOT/packages/observability/src:$ROOT/services/temporal-worker/src:$ROOT/services/edge-hub/src:$ROOT/services/outbox-dispatcher/src:$ROOT/edge/gateway/src:$ROOT/tests/integration"
```

The baseline and initial-green commands (before adding the extra test cases):

```bash
"$PYTHON" -m pytest -q -s -p no:cacheprovider \
  -W error::RuntimeWarning -W error::ResourceWarning \
  -W error::pytest.PytestUnraisableExceptionWarning \
  tests/integration/test_fleet_control_lock_order.py
```

The new bounded red probes, exit 1:

```bash
"$PYTHON" -m pytest -q -s -p no:cacheprovider \
  -W error::RuntimeWarning -W error::ResourceWarning \
  -W error::pytest.PytestUnraisableExceptionWarning \
  tests/integration/test_fleet_control_lock_order.py -k paused_resume \
  > artifacts/control-lock-order-20260929/fix/resume-inversion-red.log 2>&1
```

The original/focused probes retained unchanged in expectation, exit 0:

```bash
"$PYTHON" -m pytest -q -s -p no:cacheprovider \
  -W error::RuntimeWarning -W error::ResourceWarning \
  -W error::pytest.PytestUnraisableExceptionWarning \
  tests/integration/test_fleet_control_lock_order.py -k 'not paused_resume' \
  > artifacts/control-lock-order-20260929/fix/focused-guards.log 2>&1
```
