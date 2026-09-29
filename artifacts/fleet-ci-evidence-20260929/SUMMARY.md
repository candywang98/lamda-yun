# FLEET-CI-EVIDENCE

Date: 2026-09-29. Evidence acquisition only, NOT a latency fix.

- Baseline: `c8f0e5adfd458610f5385651dc5ee3bd3db9ab12`.
- Branch: `agent/astra-fleet-ci-evidence-20260929`.
- Reused worktree: `sol-ime-picker-20260929`.
- Before branching: exact `ae9fd7412468280fe1f2c8149678968847ec5b58`
  on `agent/sol-control-lock-order-fix-20260929`, tracked/index clean;
  38 preexisting untracked files verified against the prior hash manifest.
- Final delivery SHA is the commit adding this document, reported in the
  handoff. No main checkout edit or push is authorized/performed.

## Changed paths and frozen contract

Only:

1. `.github/workflows/ci.yml`, Python job only.
2. `tests/ops/test_ci_python_portability.py`.
3. New `tests/load/fleet/ci_diagnostics.py`.
4. New `tests/load/fleet/test_ci_diagnostics.py`.
5. This evidence directory.

The mandatory full-suite gate remains `pytest -q -rs`, with only an explicit
`--basetemp "$RUNNER_TEMP/cloudctl-pytest"` and step ID `pytest` added.
All preceding raw checks and the following security command retain their
original relative order and normal failure behavior.

One supplementary step runs only under
`failure() && steps.pytest.outcome == 'failure'`. It starts a fresh Python
process and directly awaits the original hundred-client test coroutine.
The coroutine's assertions and harness are unchanged: 100 clients, one task,
cold start, before-POST clock and p95 < 5.0, all HTTP/durable assertions.
There is no full-suite retry, gate substitution, skip, xfail, continue-on-error,
warmup, extra pacing or changed database/pool settings.

The diagnostic uses a distinct new directory, refuses existing directories
instead of deleting them, and leaves FleetPostgres's normal tempfile behavior
untouched. Its internal 180-second asyncio deadline allows normal context
cleanup; a five-minute workflow timeout provides an outer bound. Assertion,
timeout and ordinary failures produce exit 1. Cancellation/BaseException are
recorded as non-success and re-raised. Forced process/runner loss cannot
guarantee an artifact or cleanup; no such guarantee is claimed.

An `always()` upload-artifact@v4 step retains evidence seven days, named by
SHA/run/attempt. Its exact allowlist is only:

```text
${{ runner.temp }}/cloudctl-pytest/**/load-report-*.json
${{ runner.temp }}/cloudctl-fleet-diagnostic/load-report-*.json
${{ runner.temp }}/cloudctl-fleet-diagnostic/diagnostic.json
```

Missing files warn; they do not mask or convert the mandatory pytest failure.
No entire temp directory, cache, environment dump, token or source tree is
uploaded. Upload and diagnostic steps are supplementary, never acceptance.

Reference provided with the frozen design:
https://docs.github.com/en/actions/using-workflows/storing-workflow-data-as-artifacts
https://docs.github.com/en/actions/reference/evaluate-expressions-in-workflows-and-actions

## Diagnostic measurements and cleanup

The external prior probe was reviewed and adapted, not installed into normal
requests. Importing the diagnostic module installs nothing. Only the explicit
diagnostic runner or explicit lifecycle tests enter `Probe.observe()`.

- Counts actual cancel/resume/take-control, authenticate and claim calls.
- Measures actual HTTP claim, auth and claim phase wall durations.
- Counts successful claim SQL cursor statements by operation/table/lock
  category, separately reports SQL errors; no SQL parameter values retained.
- Measures `Pool.connect` total acquisition duration using its public method,
  without changing return values or exceptions. SQLAlchemy 2.0.52's exact
  implementation was inspected: total includes connection creation,
  pre-ping and checkout hooks, NOT queue-only waiting. The inspected source
  is retained in `sqlalchemy-acquire-contract.log`. Private pool fields are
  read only for provenance, not used to change behavior.
- Samples event-loop lag every 50 ms for the whole diagnostic including setup.
- Uses the repository's nearest-rank `percentile`; a two-value p95 is the max.
- Records host/Python/PG/driver/pool/SQLAlchemy provenance, not connection URLs,
  tokens, parameters or raw environment.
- Cancels and awaits the sampler, then restores all patches/listeners via
  ExitStack. Cleanup success is marked only after all callbacks succeed;
  restoration failure stays false even after a previous successful use.

The frozen normal test's before-POST timing is unchanged. Diagnostic timers
have their own overhead; concurrent wall times are not exclusive CPU, and
pool total is not a causal queue-wait attribution.

## Verification

All commands ran in the assigned worktree with main's existing dependencies.
No installations, ignore/config changes or remote workflow invocation.

| Evidence | Exit | Result |
| --- | --- | --- |
| `focused-initial.log` | 0 | 45 passed, 9.00s |
| `validation.log` | 0 | 77 passed, 49.47s |
| `validation-final.log` | 0 | 78 passed, 59.71s; final source |
| `standalone.log`, `standalone/diagnostic.json` | 0 | Real CLI, original 100-client assertions passed |
| `ruff-initial.log` | 1 | Six initial lint findings, corrected in owned code |
| `ruff-check.log` | 1 | Remaining long literal, corrected |
| `ruff-delivery.log` | 0 | Whole-worktree lint clean |
| `format-delivery.log` | 0 | 728 files already formatted |
| `mypy-diagnostic-final.log` | 0 | Both new modules clean |
| `pyright-diagnostic-final.log` | 0 | Both new modules: 0 errors/warnings |
| `mypy-configured.log` | 0 | 162 configured production files clean |
| `pyright-configured.log` | 0 | Configured production sources: 0 errors/warnings |
| `security.log` | 0 | Security boundary check passed |
| `scope-check.json` | 0 | Byte equality and ownership assertions passed |

Final regression command:

```bash
../cloudctl-source/.venv/bin/python -m pytest -q -rs -p no:cacheprovider \
  -W error::RuntimeWarning -W error::ResourceWarning \
  -W error::pytest.PytestUnraisableExceptionWarning \
  tests/ops/test_ci_python_portability.py tests/ops/test_ci_release_key.py \
  tests/load/fleet
```

The initial focused command covered the two ops files and
`tests/load/fleet/test_ci_diagnostics.py` without the strict warning flags.
The intermediate 77-test command was identical to the final command above.

The workflow tests enforce the mandatory command list/order and exact
supplementary steps, reject conditional core/job gates, skipped/replaced/retried
pytest, continue-on-error, broad upload paths, implicit-success diagnostics,
always-on diagnostics, reused gate basetemp and duplicate diagnostic steps.
The security command is selected by exact command identity, not final index.
Existing Android release-key tests are unchanged.

Lifecycle tests cover return/exception preservation, assertion/timeout/
cancellation cleanup, partial install failure, cleanup failure, reuse after
cleanup, runner exit recording, canceled-run non-success propagation and
refusal to overwrite reports. Real one-device ASGI/PG tests verify SQL/pool/
sampler output and owned PG cleanup after both assertion failure and cancellation.

CLI validation used explicit worktree source PYTHONPATH and:

```bash
../cloudctl-source/.venv/bin/python -m tests.load.fleet.ci_diagnostics \
  --basetemp "$PWD/artifacts/fleet-ci-evidence-20260929/standalone"
```

It produced the original load report and compact diagnostic JSON; cleanup
fields are true, changed-method counts zero, and pool/lag samples present.
This CLI run preceded only the defensive cleanup-flag reset and extra reuse/
real-PG cancellation test; final 78-test validation includes those changes.
Its latency is not used as performance acceptance or CI causal evidence.

Lint/format commands: main venv's `ruff check .` and `ruff format --check .`.
Diagnostic typing:

```bash
env -u MYPYPATH -u PYTHONPATH ../cloudctl-source/.venv/bin/mypy \
  --no-incremental --cache-dir=/dev/null \
  tests/load/fleet/ci_diagnostics.py tests/load/fleet/test_ci_diagnostics.py
../cloudctl-source/.venv/bin/pyright --venvpath ../cloudctl-source \
  tests/load/fleet/ci_diagnostics.py tests/load/fleet/test_ci_diagnostics.py
bash scripts/check-security-boundaries.sh
```

Configured mypy used `python -m mypy --no-incremental --cache-dir=/dev/null`,
unset MYPYPATH and explicit worktree PYTHONPATH for all ten configured package
source directories. Configured Pyright used `--venvpath ../cloudctl-source`.
These are local worktree checks, not a claim that new hosted CI ran.

### Preserved preexisting typing limitations

The expanded three-file mypy/Pyright invocations additionally included
`tests/ops/test_ci_python_portability.py` and failed. Both failures were
reproduced against main's unmodified version of that file:

- mypy: missing PyYAML stubs and existing `postgres_discovery_step` Any return.
- Pyright: existing `unavailable` possibly-unbound control-flow diagnostic.

`mypy.log`, `pyright.log`, and their `*-baseline-portability.log` comparisons
are retained. No stubs installed, type ignores added or unrelated helper
semantics changed. These test files are outside configured production typing.
New diagnostic modules and configured production gates pass separately.

## Integrity and remaining limits

`scope-check.json` confirms full byte equality against c8f0e5a for harness,
PostgreSQL fixture, original fleet tests, metrics and ledger, stronger than an
AST-only predicate check. Production diff is empty. Ledger SHA256 remains
`3a1ae74049ba843bc66a77d4a0cb98be259130897ff324b17d106e5d6bb46fcb`.
Android/frontend jobs and top-level workflow permissions/triggers are unchanged.
All 38 old worktree untracked files retain their hashes.

The failed CI run 36585191217 is not rerun or relabeled. Its initial and
terminal evidence under the existing external acceptance directory is untouched.
No performance fix or flaky classification is claimed. No new CI artifact has
yet been produced: parent must review, integrate and authorize the normal push.
No hardware, business, deployment or acceptance action is authorized by this
evidence work. Raw logs retain original diagnostics and possible trailing
blank lines; source-only whitespace checks are used separately.
