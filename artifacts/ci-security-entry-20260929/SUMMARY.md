# CI-SECURITY-ENTRY - 2026-09-29

## Scope and Baseline

- Frozen baseline: `226eff2ff472459603af9c6e4a01f4e92dce7ebd`.
- Branch: `agent/sol-ci-security-entry-20260929`, created directly from that
  baseline in the existing `sol-ime-picker-20260929` worktree.
- Owned files: `.github/workflows/ci.yml`,
  `tests/ops/test_ci_python_portability.py`, and this summary.
- The prior untracked `artifacts/ime-picker-recovery-20260929/` and
  `artifacts/publish-permissions-20260929/` directories are preserved.
- No security-script contents, mode, rules, production code, other workflow
  gates, ledger, Android configuration, or trust/public-key configuration changed.
  No keys were generated or installed. No push, remote API/network, other-chat,
  device, ADB/SSH, deployment, or real business operation was performed.
- The final handoff reports the SHA of the commit containing this summary.

## Hosted Evidence Supplied by Controller

This worker did not fetch the hosted run. The controller supplied:

- Run `36564799780` at `eb1eedc`, Python job `109393998994`.
- Python pytest: **1624 passed, 14 skipped in 372.71s**. PostgreSQL binaries
  were found under `/usr/lib/postgresql/16/bin`; prior portability/Q02 and
  fleet tests passed.
- Frontend: **624 Web + 16 Studio** tests passed.
- The subsequent security step failed at
  `2026-09-29T12:03:18.2291354Z`: direct invocation of
  `scripts/check-security-boundaries.sh` returned **126**, `Permission denied`.
- The controller's local explicit Bash invocation passed.

This change addresses that entry-point failure only. It does not reinterpret
the successful hosted pytest result or claim that the changed commit has
already passed hosted CI.

## Change and Executable Proof

The only workflow edit is:

```diff
-      - run: scripts/check-security-boundaries.sh
+      - run: bash scripts/check-security-boundaries.sh
```

Full-history checkout, PostgreSQL discovery, `pytest -q -rs`, gate order,
frontend/Android jobs, and error handling are unchanged. The existing exact
gate-list assertion now expects the explicit Bash command.

The new two-case regression parses the actual last Python job command from
the workflow YAML and executes it against a disposable repository layout:

1. Copy the unchanged guard, explicitly chmod the copy to `0644`, and assert
   both its mode and byte-for-byte identity with the source.
2. Create the required empty `infra`, `services`, and `apps` directories.
3. Write either a benign Python file or a forbidden LAMDA import under
   `services`. The violation is assembled from separate tokens so the guard
   does not flag the regression-test source itself.
4. Prove the old direct command returns **126** with `Permission denied`.
5. Execute the parsed workflow command with Bash `-e -o pipefail`.
   The benign fixture must return **0** with
   `Security boundary checks passed.` and empty stderr.
   The forbidden fixture must return **1**, empty stdout, and the exact
   diagnostic beginning
   `LAMDA import outside packages/lamda-driver: ./services/probe.py:1:`.

There are no skipped cases, ignored failures, stubbed guard implementations,
or guard-rule changes. `check=False` captures subprocess status for explicit
assertions; it does not turn failures into success.

Local shell calibration: macOS `/bin/bash` **3.2.57** reports a non-executable
command as status 1 when its outer shell has `-e`; without outer `-e`, the raw
command status is 126. An initial draft caught this difference (two failed
tests in 0.09s, exit 1). Only the old-command negative control omits outer
`-e` to assert raw status 126. The actual workflow command is always exercised
with strict outer-shell flags, and the unchanged guard retains
`set -euo pipefail`. No status assertion is relaxed.

## Local Commands and Results

Environment: macOS **26.0 arm64**, main `cloudctl-source/.venv`, Python
**3.13.5**, pytest **9.1.1**, PyYAML **6.0.3**, Ruff **0.16.5**.
Commands run from the assigned worktree, with an explicit worktree source path:

```sh
ROOT="$(git rev-parse --show-toplevel)"
PYTHON="$ROOT/../cloudctl-source/.venv/bin/python"
export PYTHONPATH="$ROOT/packages/domain/src:$ROOT/packages/edge-protocol/src:$ROOT/packages/lamda-driver/src:$ROOT/packages/automation-sdk/src:$ROOT/packages/observability/src:$ROOT/services/control-api/src:$ROOT/services/temporal-worker/src:$ROOT/services/edge-hub/src:$ROOT/services/outbox-dispatcher/src:$ROOT/edge/gateway/src"
```

### Red Before the Workflow Edit

With the final regression in place but the frozen direct workflow command
still unchanged:

```sh
"$PYTHON" -m pytest -q \
  tests/ops/test_ci_python_portability.py::test_parsed_security_gate_runs_nonexecutable_guard \
  --show-capture=no
```

**2 failed in 0.09s, exit 1.** Both raw-direct status-126 assertions passed.
The benign case failed because the parsed gate could not execute the guard;
the forbidden case rejected `Permission denied` as a substitute for the
required security diagnostic.

### Green After the One-Line Workflow Edit

```sh
"$PYTHON" -m pytest -q \
  tests/ops/test_ci_python_portability.py tests/ops/test_ci_release_key.py \
  --show-capture=no
```

**21 passed in 11.13s, exit 0; no skips.** This includes both new executable
cases, existing history/PostgreSQL-discovery tests, exact workflow gates,
and existing release-public-key tests. Release-key fixtures use a sentinel,
not generated key material.

```sh
"$PYTHON" -m ruff check \
  tests/ops/test_ci_python_portability.py tests/ops/test_ci_release_key.py
"$PYTHON" -m ruff format --check \
  tests/ops/test_ci_python_portability.py tests/ops/test_ci_release_key.py
bash scripts/check-security-boundaries.sh
git diff --check
git diff --exit-code 226eff2ff472459603af9c6e4a01f4e92dce7ebd -- scripts/check-security-boundaries.sh
git ls-files -s scripts/check-security-boundaries.sh
```

All exit **0**. Ruff lint: `All checks passed!`; format: **2 files already
formatted**. The exact new guard invocation on the real worktree prints
`Security boundary checks passed.` The guard diff is empty, filesystem mode
remains **0644**, and the Git index entry remains:

```text
100644 6692349ef9b120672b003cb8e029fa023eb2a25a 0 scripts/check-security-boundaries.sh
```

## Handoff Limits

No broad Python, frontend, Android, or repeated load suite was rerun for this
single-entry fix. The hosted full-suite figures above are controller-supplied
evidence for the earlier run, not a new local or hosted run on this commit.
The controller owns integration, hosted CI confirmation, and pushing.
