# Fleet Load Isolation - 2026-09-29

## Delivery Boundary

- Work item: `fleet-load-isolation-20260929`.
- Frozen baseline: `c7bde6b9745a623068e9f02f4b6af110098405db`.
- Branch: `agent/sol-load-isolation-20260929`, existing `sol-ime-picker-20260929` worktree.
- Owned changes: `tests/load/fleet/harness.py`, `tests/load/fleet/test_fleet_load.py`,
  new `test_harness_isolation.py` and `test_harness_diagnostics.py` in that directory,
  and this summary.
- No production, database/settings, schema, CI, workflow, lock-script, or controller
  evidence-index changes. No rebase, push, other-chat, network, device, installation,
  deployment, or real business operations. Databases are disposable local fixtures.
- The existing untracked `artifacts/ime-picker-recovery-20260929/` and
  `artifacts/publish-permissions-20260929/` directories are not part of this change.
- The delivery SHA is the commit containing this summary and is reported in the
  final handoff.

## Findings and Evidence Limits

The controller reported GitHub run `36556566588` at the frozen baseline failing
`test_baseline_two_devices_twenty_tasks_report` with one outcome at
`claimed=12, completed=12, errors=[], stranded=0`. The controller's eight exact
local baseline-node repetitions passed in approximately 1.4-1.8 seconds.
**The exact remote 12/20 symptom has not been reproduced.**

A different, deterministic defect is proven: the original harness's in-memory
SQLite `StaticPool` shares one physical connection across overlapping sessions.
The new controlled tests hold the real API transaction after flush and before
commit, use another session to read and roll back, then let the API finish.
Against the unchanged frozen harness:

| API operation | Expected observer / final state | Actual observer / final state | HTTP |
| --- | --- | --- | --- |
| claim | `QUEUED` / `CLAIMED` | `CLAIMED` / `QUEUED` | 200 |
| complete | `CLAIMED` / `SUCCEEDED` | `SUCCEEDED` / `CLAIMED` | 200 |

Thus both dirty visibility and foreign-session rollback followed by a successful
API acknowledgement are demonstrated. This is a fixture isolation failure, not evidence
that the production API has the same defect, nor proof of the precise remote
failure sequence. With the file-backed fixture the same two tests pass: observers
see only prior committed state; their rollback does not undo claim/completion;
the committed lease matches the API response.

Read-only call-chain review:

- `mobile_routes.py` authenticates the Companion binding before invoking task
  claim/event/heartbeat/completion handlers.
- `MobileTaskService.authenticate` has its own unit of work and updates binding
  and device `last_seen_at`.
- `claim` has a separate unit of work for task state, device fencing, lease and
  recipe audit. `event` persists its event row and task sequence together.
- `heartbeat` changes the stranded task to `RUNNING` and renews its lease.
- `finish` writes terminal state, runs reply-settlement queries (which can
  autoflush), and cancels the matching device lease in its unit of work.
- `Database.unit_of_work` uses a session plus `session.begin()`. Independent
  session objects cannot supply independent transactions on one shared physical
  SQLite connection.
- `release` requires an explicit supported accessibility reason. The old harness
  sent a reason-less release after completion errors; that request was invalid.

New diagnostics also uncovered an independent existing harness error:
`PROGRESS` is not a permitted `MobileTaskEvent.event_type`. It produced 422s
that the harness ignored. This explains the intermediate two test failures after
strengthening error assertions, not the remote incomplete-task symptom.

## Changes

1. `FleetLoadApp` now uses a `TemporaryDirectory` and the existing file-backed
   SQLite settings pattern also used in `test_backend_outbox.py`. Its
   `AsyncExitStack` closes the HTTP client and app lifespan/database connections
   before deleting the temporary directory. The object store remains in memory.
2. Report metadata says `repositoryMode=sqlite`, `engine=temporary-file-sqlite`,
   and includes the actual pool class (`AsyncAdaptedQueuePool` locally).
   Explicit limitations distinguish this from PostgreSQL row-lock, network,
   multi-node, and hardware evidence. Test reports use pytest `tmp_path`, not the
   tracked D11 evidence directory.
3. Workers record claim attempts, per-operation HTTP status counts, all errors,
   acknowledged-complete/stranded/remaining task IDs, and guard exhaustion.
   A read-only reconciliation after concurrent workers finish adds durable task
   status, business state, attempt, sequence, lease, and error-code evidence.
   A 200 completion without durable success is reported as an error.
4. Unexpected guard exhaustion is explicit, with remaining work, status counts
   and persisted task states. A 5xx is retained as an error, not relabeled as
   proven lease contention. Persistent completion failures keep lease evidence
   and stop the worker instead of sending the invalid release request.
5. Intended failed-device semantics remain explicit: one heartbeat-confirmed
   stranded `RUNNING` task and the remaining `QUEUED` tasks report
   `intentional-device-failure`, not accidental partial success.
6. The synthetic progress event now uses the existing legal `STEP_STARTED`
   value. Baseline and 100-client assertions require event 201 responses and
   persisted `lastSequence=1` along with complete successful outcomes.

Unchanged: concurrent worker `asyncio.gather`, 2x20 baseline task count,
100 concurrent simulated workers, guard `tasks_per_device * 30 + 50`, existing
claim pacing/backoff values, the existing single completion retry,
100-client claim p95 `< 5.0s`, healthy HOL claim p95 `< 2.0s`, and UNKNOWN
control-event evidence-retention assertions. No new locks, serialization,
delays, retries, skips, xfails, or reduced workloads were introduced.

## Executed Verification

Environment: main `cloudctl-source/.venv`, Python **3.13.5**, macOS
**26.0 arm64**, SQLite **3.47.1**, SQLAlchemy **2.0.52**, aiosqlite **0.22.1**,
FastAPI **0.141.1**, HTTPX **0.28.1**, pytest **9.1.1**, pytest-asyncio **1.4.0**,
Ruff **0.16.5**, mypy **2.3.1**.
Runtime `cloudctl_api.__file__` and `cloudctl_api.db.__file__` were checked and
resolved to this worktree, not the main checkout.

All commands below run from the assigned worktree with:

```sh
ROOT="$(git rev-parse --show-toplevel)"
PYTHON="$ROOT/../cloudctl-source/.venv/bin/python"
export PYTHONPATH="$ROOT/packages/domain/src:$ROOT/packages/edge-protocol/src:$ROOT/packages/lamda-driver/src:$ROOT/packages/automation-sdk/src:$ROOT/packages/observability/src:$ROOT/services/control-api/src:$ROOT/services/temporal-worker/src:$ROOT/services/edge-hub/src:$ROOT/services/outbox-dispatcher/src:$ROOT/edge/gateway/src"
```

### Deterministic Frozen-Baseline Red

No tracked file is reverted or overwritten. This loads the frozen harness in
memory and substitutes only that harness into the new isolation tests:

```sh
"$PYTHON" - <<'PY'
import subprocess
import sys
import types
import pytest

baseline = types.ModuleType("frozen_memory_harness")
sys.modules[baseline.__name__] = baseline
source = subprocess.check_output(
    ["git", "show", "c7bde6b9745a623068e9f02f4b6af110098405db:tests/load/fleet/harness.py"],
    text=True,
)
exec(compile(source, "<frozen-memory-harness>", "exec"), baseline.__dict__)

class FrozenHarness:
    def pytest_collection_modifyitems(self, items):
        for item in items:
            item.module.FleetLoadApp = baseline.FleetLoadApp

raise SystemExit(pytest.main(
    ["-q", "tests/load/fleet/test_harness_isolation.py", "--show-capture=no"],
    plugins=[FrozenHarness()],
))
PY
```

Result: **2 failed, 1 warning in 0.58s; exit 1**. Both failures are the state
pairs shown above, after asserting HTTP 200. The warning is pytest's
already-imported `anyio` assertion-rewrite warning from this in-process runner;
it is not the failure mechanism.

### Green and Diagnostic Tests

```sh
"$PYTHON" -m pytest -q tests/load/fleet --show-capture=no
```

- Intermediate fixture-only stage: **9 passed in 19.17s**, exit 0.
- After new error assertions, before fixing invalid `PROGRESS`: **2 failed,
  12 passed in 25.45s**, exit 1. Only baseline/100-client empty-error assertions
  failed because event requests returned 422; completion counts had passed.
- After the legal event fix and durable-sequence assertions: **14 passed in
  22.52s**, exit 0.

The five focused repetitions each run this exact command in a fresh process:

```sh
"$PYTHON" -m pytest -q \
  tests/load/fleet/test_fleet_load.py::test_baseline_two_devices_twenty_tasks_report \
  tests/load/fleet/test_harness_isolation.py \
  tests/load/fleet/test_harness_diagnostics.py --show-capture=no
```

Results: **8 passed** each in **6.18s, 6.85s, 8.40s, 6.78s, 6.20s**; all
five exit codes **0** (40 test executions). Coverage includes real
claim/completion isolation, deterministic claim 204/409/500 guard exhaustion,
forged completion 200 without persistence, and persistent completion 409
without an invalid release. The HTTP faults are explicit harness fault
injections, not claims of production reproduction.

Three further full-directory repetitions used fresh pytest processes and a new
temporary base directory per run:

```sh
"$PYTHON" - <<'PY'
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

for iteration in range(1, 4):
    with TemporaryDirectory(prefix="fleet-verify-") as root:
        result = subprocess.run([
            sys.executable, "-m", "pytest", "-q", "tests/load/fleet",
            "--show-capture=no", "--basetemp", str(Path(root) / "pytest"),
        ])
        if result.returncode:
            raise SystemExit(result.returncode)
PY
```

The executed runner also parsed each generated JSON report before removing its
temporary directory. No run depended on prior-run reports. Rounded latency
values below come from those report JSONs:

| Full repeat | Result | Exit | Baseline claim p95 | 100-client claim p95 | Healthy HOL claim p95 |
| --- | --- | --- | --- | --- | --- |
| 1 | 14 passed in 25.33s | 0 | 0.032269s | 1.092637s | 0.112805s |
| 2 | 14 passed in 26.74s | 0 | 0.026362s | 1.589124s | 0.028187s |
| 3 | 14 passed in 23.50s | 0 | 0.026864s | 0.960793s | 0.022244s |

Each full repeat had 40/40 baseline completions and 100/100 scale completions,
with zero errors and zero remaining tasks in those two scenarios. Each HOL
run had 10/10 healthy-device completions, one intentionally stranded task and
nine queued tasks on the failed device, with no unexpected errors. Guard
fault-injection scenarios intentionally reported errors and passed their
diagnostic assertions. UNKNOWN evidence retention and all three metrics tests
also passed in every full run.

On the final code: the first full green run plus these three repetitions and
five focused runs total **96 passed test executions**, all exit 0. There are
**no currently failing tests** in the scoped fleet suite; the frozen-baseline
red run remains intentionally failing evidence.

### Static Checks

```sh
"$PYTHON" -m ruff check tests/load/fleet
"$PYTHON" -m ruff format --check tests/load/fleet
MYPYPATH="$PYTHONPATH" "$PYTHON" -m mypy --follow-imports=silent \
  tests/load/fleet/harness.py tests/load/fleet/test_fleet_load.py \
  tests/load/fleet/test_harness_isolation.py tests/load/fleet/test_harness_diagnostics.py
git diff --check
```

Results: all exit **0**; Ruff lint clean, **6 files already formatted**, mypy
**no issues in 4 source files**. This is explicitly scoped mypy with the
worktree `MYPYPATH` and `--follow-imports=silent`, not raw integrated-main CI
equivalence.

## Residual Limits

- Linux/GitHub confirmation remains for the controller after integration. The
  local passing tests do not retroactively explain the exact remote 12/20 run.
- File-backed SQLite supplies independent transaction connections for this
  harness but is not PostgreSQL row-lock or production performance evidence.
  Reported latency includes SQLite connection-pool/writer contention.
- These are simulated ASGI clients, not networked clients or physical devices.
  No hardware acceptance, device readiness, TLS/signature, or real publishing
  result is asserted.
- No API defect requiring production edits was established by these local
  tests. If isolated-fixture Linux CI still loses work, its enriched report
  should support a separate minimal reproduction and production-scope handoff.
