# CI Python portability, 2026-09-29

## Scope and outcome

- Branch: `agent/sol-ci-portability-20260929`.
- Frozen parent: `c7bde6b9745a623068e9f02f4b6af110098405db`.
- Worktree: `/Users/wangziheng/Desktop/01-主战场/LAMDA云控系统/sol-publish-queue-20260929`.
- Lock-tool change: add only the exact GNU stat token `ext2/ext3` to
  `scripts/device_lock.py:LOCAL_FSTYPES`; retain all classifier, network refusal,
  unknown-type refusal, locking, ownership, and fencing logic.
- Test changes: 4 positive Linux stat cases and 19 negative cases; independently
  build the two expected APK paths from `Path.home()` and literal relative
  suffixes, retaining the exact serial and all six argv elements.
- Workflow change: `fetch-depth: 0` on the Python job's checkout only.
  Q02's original guard and frozen expected SHA remain untouched.
- New workflow tests parse YAML, preserve every existing Python gate and other
  checkouts, and exercise real Git ancestry in disposable local full/shallow clones.
- PostgreSQL PATH setup is proposed below, NOT applied without controller approval.

Only the seven authorized paths are intended for this commit: `scripts/device_lock.py`,
`tests/ops/test_device_lock.py`, `tests/ops/test_oneplus_v5_acceptance.py`,
`tests/ops/test_oneplus_v6_acceptance.py`, `.github/workflows/ci.yml`,
`tests/ops/test_ci_python_portability.py`, and this summary.
No OnePlus installer/helper changes, dependency installs, GitHub variable/secret or
production-configuration changes, task-ledger changes, other-chat operations,
production/hardware/ADB/SSH/deployment operations, or push. Lock tests use
disposable databases and fictional test serials; the shared device-lock database
is not used.

## Verified causes and regression evidence

Controller-provided terminal run `36556566588` at `c7bde6b`:
**22 failed, 1361 passed, 171 skipped, 42 errors**. These remote counts are not
results of this worker's local runs.

1. **Filesystem alias:** injected the actual reported GNU stat output
   `ext2/ext3\n` through `_run_fixed` with Linux classification selected.
   Baseline `_assert_local_file` refused it with code 5. Before the source fix,
   the new Linux cases produced **1 failed, 22 passed**: only the alias failed.
   The change is one exact allowlist entry, not slash splitting or prefix
   acceptance. Negative coverage includes NFS, CIFS, SSHFS, unknown FUSE,
   unclassified/empty output, `ext2/nfs`, `ext2/ext3/nfs`, `ext2/ext3/ext4`,
   `ext2/ext3evil`, `ext2/ext30`, whitespace, and multiple lines. Failures remain
   `EXIT_USAGE`; no database is created by classification tests.
2. **Home portability:** before changing tests, running their two argv assertions
   with `HOME=/home/runner` produced **2 failed**, exit 1: actual paths correctly
   began with `/home/runner`, but expectations began with `/Users/wangziheng`.
   After changing expectations only, the same two tests passed; all **145**
   fake-only v5/v6 tests also passed under that HOME. Expected paths are NOT
   derived from `acceptance.APK`; literal versions, filenames, serial and flags
   remain asserted. Neither ADB nor the helpers' operational entrypoints ran.
3. **History:** the controller verified the exact CI checkout log reports
   `fetch-depth: 1` and
   `/usr/bin/git ... fetch --no-tags --prune --no-recurse-submodules --depth=1 origin +c7bde6b...:refs/remotes/origin/main`
   (ellipses retained from the controller's quoted log; no full command invented).
   This is controller-supplied runner evidence, not an independent remote read
   by this worker. Local
   `git merge-base --is-ancestor 29f19dd0160c9f309ebf86c1cf3c118174a2fc9f c7bde6b9745a623068e9f02f4b6af110098405db`
   returned 0. The new workflow regression reproduced an unavailable ancestor
   (Git exit 128) using a local depth-1 clone; before the workflow edit its suite
   had **2 failed, 1 passed**, exit 1. Full history passes the same real Git
   proof. Existing Q02 software scenarios now pass **42/42** locally with their
   original fixture, original expected SHA and no expected-SHA environment override.
   No Q02 code, SHA file, assertion, skip condition or environment shortcut changed.

## Reproduction environment and commands

All commands run from the worktree above. Main-checkout tools are pinned Ruff
0.16.5, Mypy 2.3.1, Pyright 1.1.411, pytest 9.1.1, PyYAML 6.0.3.
Local Python is **3.13.5 on macOS**, whereas the workflow requests Python 3.12
on `ubuntu-latest`; injected Linux stat output and a simulated HOME do not
constitute a completed Linux CI run.

Shell definitions for the exact commands below:

```bash
MAIN=/Users/wangziheng/Desktop/01-主战场/LAMDA云控系统/cloudctl-source
VENV="$MAIN/.venv"
OPS=(
  tests/ops/test_device_lock.py
  tests/ops/test_oneplus_v5_acceptance.py
  tests/ops/test_oneplus_v6_acceptance.py
  tests/ops/test_ci_python_portability.py
  tests/ops/test_ci_release_key.py
)
Q02=(
  tests/parallel_acceptance/q02/test_s01_intent_order.py
  tests/parallel_acceptance/q02/test_s02_readback_confirmation.py
  tests/parallel_acceptance/q02/test_s03_lost_ack_idempotency.py
  tests/parallel_acceptance/q02/test_s04_cancel_matrix.py
  tests/parallel_acceptance/q02/test_s05_stale_lease_fencing.py
  tests/parallel_acceptance/q02/test_s06_reconciliation_branches.py
  tests/parallel_acceptance/q02/test_s07_same_task_recovery.py
)
```

| Command | Exit | Actual result |
|---|---:|---|
| `env PYTHONDONTWRITEBYTECODE=1 "$VENV/bin/python" -m pytest -q -p no:cacheprovider "${OPS[@]}"` | 0 | Final recheck: 200 passed in 4.54s; no skips. |
| `env -u Q02_DEVICE_SERIAL -u Q02_BASE_URL -u Q02_EXPECTED_SHA PYTHONDONTWRITEBYTECODE=1 "$VENV/bin/python" -m pytest -q -p no:cacheprovider "${Q02[@]}"` | 0 | Final recheck: 42 passed in 9.98s; no skips; software files only, not device scenarios. |
| `env HOME=/home/runner PYTHONDONTWRITEBYTECODE=1 "$VENV/bin/python" -m pytest -q -p no:cacheprovider tests/ops/test_oneplus_v5_acceptance.py tests/ops/test_oneplus_v6_acceptance.py` | 0 | Final recheck: 145 passed in 0.13s; overlaps OPS, not additional distinct tests. |
| `"$VENV/bin/ruff format --check ."` | 0 | Final recheck: 704 files already formatted. |
| `"$VENV/bin/ruff check ."` | 0 | All checks passed. |
| `env -u PYTHONPATH -u MYPYPATH PYTHONDONTWRITEBYTECODE=1 "$VENV/bin/mypy"` | 0 | No issues in 162 configured source files; main editable-install caveat below. |
| `env -u PYTHONPATH -u MYPYPATH PYTHONDONTWRITEBYTECODE=1 "$VENV/bin/pyright" --project "$PWD/pyproject.toml" --venvpath "$MAIN"` | 0 | 0 errors, 0 warnings, 0 informations. |
| `bash scripts/check-security-boundaries.sh` | 0 | Security boundary checks passed. |
| `git diff --check` | 0 | No whitespace errors. |
| `git diff --exit-code c7bde6b9745a623068e9f02f4b6af110098405db -- artifacts/three-device-20260928 tests/parallel_acceptance/q02 mobile pyproject.toml docs/current/tasks.json` | 0 | Installers, Q02 guard/fixture/SHA, Android production sources, gate configuration and task ledger unchanged. |

The raw Mypy invocation uses the existing main `.venv` editable installation,
without `PYTHONPATH/MYPYPATH` overrides or any install. Its configured package
scope excludes `scripts/` and tests. It is not presented as an isolated
installation of this worker's checkout. Pyright uses this worktree's explicit
project configuration and main dependency venv.

An additional strict script check, outside the workflow's configured package
scope, returned 1:

```text
$ env -u PYTHONPATH -u MYPYPATH PYTHONDONTWRITEBYTECODE=1 \
    "$VENV/bin/mypy" --cache-dir=/dev/null scripts/device_lock.py
scripts/device_lock.py:298: error: Incompatible types in assignment (expression has type "list[str]", variable has type "str")  [assignment]
scripts/device_lock.py:503: error: Returning Any from function declared to return "Row | None"  [no-any-return]
Found 2 errors in 1 file (checked 1 source file)
```

The exact frozen source reproduced both diagnostics at lines 297 and 502, exit 1:

```bash
git show c7bde6b9745a623068e9f02f4b6af110098405db:scripts/device_lock.py |
  env -u PYTHONPATH -u MYPYPATH PYTHONDONTWRITEBYTECODE=1 \
  "$VENV/bin/mypy" --cache-dir=/dev/null \
  --shadow-file scripts/device_lock.py /dev/stdin scripts/device_lock.py
```

These pre-existing diagnostics were not swept into the exact-alias repair.
A superseded attempt using `mypy -c` returned 2 because configured package
targets conflict with the command target; the shadow-file check above replaced
that invalid invocation. No type-check settings or ignores changed.

## PostgreSQL discovery: controller approval required

Six existing integration fixture modules check `shutil.which` for `initdb`,
`pg_ctl`, and `createdb`, then skip when unavailable:
`test_fleet_cancel_reconcile.py:96`, `test_controlled_fault_matrix.py:279`,
`test_xianyu_publish_dispatch.py:55`, `test_fleet_two_devices.py:106`,
`test_p14_recipe_versions.py:44`, and `test_fleet_claim_recovery.py:76`
(all under `tests/integration/`, frozen baseline).

Local read-only lookup found all four tools (`pg_config`, `initdb`, `pg_ctl`,
`createdb`) in `/opt/homebrew/bin`. This says NOTHING about runner availability.
No saved binary inventory for run `36556566588` was found in the available
local evidence. The reported remote 171 skips versus local 14 is a gap to
investigate with skip reasons, not proof that every extra skip is PostgreSQL.

Proposed Python-only step before pytest, pending controller approval:

```yaml
- name: Discover PostgreSQL test binaries
  shell: bash
  run: |
    pg_bin="$(pg_config --bindir)" || {
      echo "::error::Cannot locate PostgreSQL test binaries via pg_config --bindir"
      exit 1
    }
    for tool in initdb pg_ctl createdb; do
      test -x "$pg_bin/$tool" || { echo "::error::Missing $tool in $pg_bin"; exit 1; }
    done
    printf '%s\n' "$pg_bin" >> "$GITHUB_PATH"
```

This uses already installed binaries, fails if discovery/tools are missing, and
does not start PostgreSQL or install packages. Proposed tests in the owned new
test file would parse and execute the exact step using fake `pg_config` and
executable fixture files: complete directory writes the precise PATH entry;
missing tool or missing `pg_config` exits nonzero without writing a success
entry. Subsequent runner verification must show actual binary paths and rerun
the existing disposable real-PostgreSQL tests; no replaced tests or relaxed skips.
Workflow remains checkout-only until that approval.

## Remaining gaps and handoff

- Controller owns the remaining load-test failure; neither load code nor its
  thresholds were changed or executed by this worker.
- PostgreSQL discovery proposal remains unimplemented pending approval and
  runner evidence; do not claim the remote skip gap is fixed.
- Android still requires the OWNER's controlled update public key. Existing
  mapping, missing-key failure, Gradle verifier and full Android suites remain
  untouched. No key was generated/configured and no Gradle task ran.
- A new complete hosted CI run is still required after controller integration;
  no full-suite rerun or push was performed here.
