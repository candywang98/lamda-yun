# ci-python-gates-20260929

Date: 2026-09-29

## Scope and baseline

- Worktree: `/Users/wangziheng/Desktop/01-主战场/LAMDA云控系统/sol-publish-queue-20260929`
- Branch: `agent/sol-ci-python-20260929`
- Frozen baseline: `7ee8424043f3f67e73f5284b4e4ff6a595a7ff8c`
- Formatting ownership was limited to the five Python helpers under
  `artifacts/three-device-20260928/` and the two OnePlus acceptance tests declared by the
  controller.
- Additional ownership was limited to `.github/workflows/ci.yml`,
  `tests/ops/test_ci_release_key.py`, and `docs/runbooks/android-ci.md`.
- No operational helper was executed. No Gradle task, release, deploy, install, SSH, ADB, device,
  publish, send, rebind, GitHub variable/secret mutation, or production operation was performed.

Main-checkout toolchain used from
`/Users/wangziheng/Desktop/01-主战场/LAMDA云控系统/cloudctl-source/.venv`:

- Python 3.13.5
- Ruff 0.16.5
- Pyright 1.1.411
- Mypy 2.3.1
- Pytest 9.1.1

All Python commands ran from the designated worktree. Test and type-check commands used explicit
worktree source paths in `PYTHONPATH`/`MYPYPATH`; Pyright used the worktree `pyproject.toml` and the
main-checkout virtual-environment path.

## Mechanical formatting and AST equivalence

Before formatting, pinned Ruff reported exactly seven files would be reformatted. After running
Ruff 0.16.5 on only those paths, all seven parsed successfully and their location-independent AST
dumps were byte-for-byte equal to the baseline AST dumps. Node counts, assertion counts, and AST
SHA-256 values were unchanged:

| Path | AST SHA-256 | Nodes | Assert nodes before/after | Equivalent |
|---|---|---:|---:|---|
| `artifacts/three-device-20260928/cloud-preflight.py` | `3311e1c088d43d22b20cea7161cc21ea6e0aab4dc08c14ede95cb72b6a68c907` | 566 | 1 / 1 | yes |
| `artifacts/three-device-20260928/install-oneplus-v5.py` | `fe791fe805146a31da8a1e3cfe0ac8b5a7540d9ed6e5e98d5c3b2d70b27acf53` | 5878 | 6 / 6 | yes |
| `artifacts/three-device-20260928/install-oneplus-v6.py` | `acf5045bda5571dc669b5149081cb9c2cb0d47db52884153deea3a7c935601b3` | 6119 | 6 / 6 | yes |
| `artifacts/three-device-20260928/oneplus-v5-cloud.py` | `e69ee17d5109c6930acb85feb2ed20843e36076357e6a823456631c5a9a37add` | 1893 | 12 / 12 | yes |
| `artifacts/three-device-20260928/oneplus-v6-cloud.py` | `e5d646b3ae866434b6a8e467d991c5d419edf470adbcb72a9bb2c170b4d5fd7e` | 1961 | 15 / 15 | yes |
| `tests/ops/test_oneplus_v5_acceptance.py` | `becd0e09407fc0bf01ff52054c202fdfa931a78a8efee70c3438e40564c612d1` | 3057 | 60 / 60 | yes |
| `tests/ops/test_oneplus_v6_acceptance.py` | `d6d0244af119f115a758fe9ac76f17e8c509b1d8cad08022d1dbf8874c1071ab` | 3695 | 70 / 70 | yes |

The seven-file formatting diff is mechanical only: 84 insertions and 129 deletions. No test
assertion or executable AST node changed.

## Android CI input boundary

- The Android job now maps only
  `${{ vars.CLOUDCTL_APP_UPDATE_PUBLIC_KEY }}` to `CLOUDCTL_APP_UPDATE_PUBLIC_KEY`.
- A first-step Bash guard rejects an absent or empty value without printing the value.
- The workflow invokes the existing `verifyReleaseUpdatePublicKey` Gradle task before preserving the
  exact full commands `cd mobile/companion && ./gradlew lint test` and
  `cd mobile/dpc && ./gradlew lint test`.
- Four parser/static tests prove the exact variable mapping, guard ordering and no-key echo, absence
  of `continue-on-error`/task exclusions/`|| true`, unchanged full Android commands, and retention of
  the existing Base64/X.509 Ed25519/RFC-test-key Gradle checks and `preReleaseBuild` dependency.
- `docs/runbooks/android-ci.md` assigns the input to the Android release OWNER and requires a
  controlled Base64 DER SPKI Ed25519 public key, never private material, with decoded fingerprint,
  provenance, environment, and approval review before configuration or rotation.

## Commands and results

`VENV` below means
`/Users/wangziheng/Desktop/01-主战场/LAMDA云控系统/cloudctl-source/.venv`.

| Command | Return code | Result |
|---|---:|---|
| `$VENV/bin/ruff format --check <seven owned Python files>` | 1 | Expected baseline failure: exactly 7 files would be reformatted. |
| `$VENV/bin/ruff check <seven owned Python files>` | 0 | All checks passed before formatting. |
| `$VENV/bin/ruff format <seven owned Python files>` | 0 | Exactly 7 files reformatted. |
| Baseline-vs-worktree `ast.parse`/`ast.dump(..., include_attributes=False)` comparison | 0 | 7/7 equivalent; hashes and assertion counts shown above. |
| `$VENV/bin/ruff format --check <seven owned Python files>` | 0 | 7 files already formatted. |
| `$VENV/bin/ruff check <seven owned Python files>` | 0 | All checks passed. |
| `$VENV/bin/pytest -q tests/ops/test_oneplus_v5_acceptance.py tests/ops/test_oneplus_v6_acceptance.py` | 0 | 145 passed in 0.19s; fake-only tests. |
| `$VENV/bin/pytest -q tests/ops/test_ci_release_key.py` | 0 | 4 passed in 0.04s. |
| `$VENV/bin/pytest -q tests/ops/test_ci_release_key.py tests/ops/test_oneplus_v5_acceptance.py tests/ops/test_oneplus_v6_acceptance.py` | 0 | 149 passed in 0.15s. |
| `$VENV/bin/ruff format --check .` | 0 | 700 files already formatted. |
| `$VENV/bin/ruff check .` | 0 | All checks passed; no next Ruff blocker remains in this checkout. |
| `$VENV/bin/pyright --project "$PWD/pyproject.toml" --venvpath /Users/wangziheng/Desktop/01-主战场/LAMDA云控系统/cloudctl-source` | 0 | 0 errors, 0 warnings, 0 information. |
| `$VENV/bin/mypy --config-file "$PWD/pyproject.toml"` with explicit worktree `MYPYPATH` | 1 | 2 existing out-of-scope `unused-ignore` errors; exact diagnostics below. |
| `bash scripts/check-security-boundaries.sh` | 0 | Security boundary checks passed. |
| `git diff --check` | 0 | No whitespace errors at review time. |

One superseded Pyright invocation attempted both `--pythonpath` and `--venvpath`; Pyright rejected
that mutually exclusive parameter combination with return code 4. The corrected command above
returned 0 with no diagnostics.

## Initial blockers before follow-up handoff

At commit `bd62e6f`, full Mypy was red for two files outside the initial work item's ownership:

```text
services/edge-hub/src/cloudctl_edge_hub/main.py:14: error: Unused "type: ignore" comment  [unused-ignore]
services/control-api/src/cloudctl_api/fleet_live.py:47: error: Unused "type: ignore" comment  [unused-ignore]
Found 2 errors in 2 files (checked 162 source files)
```

Those files were diagnosed read-only in the initial work and were not changed in `bd62e6f`. The
controller subsequently approved the narrow follow-up handoff recorded below.

## Controller-provided baseline GitHub evidence

The controller independently supplied the following authenticated, read-only evidence for baseline
`7ee8424`; this worker did not access or mutate GitHub configuration:

- GitHub Actions run `36551786225`: frontend succeeded; Python failed at Ruff formatting.
- Android job `109351440672`: completed with failure.
- The Android log contains `':app:verifyReleaseUpdatePublicKey FAILED'` and
  `'Set CLOUDCTL_APP_UPDATE_PUBLIC_KEY or -Pcloudctl.appUpdatePublicKey for release.'`
- Repository-variable API returned HTTP 200 with `total_count=0`; the specific
  `CLOUDCTL_APP_UPDATE_PUBLIC_KEY` variable and secret metadata returned HTTP 404.
- The baseline workflow did not map any repository variable into the Android job.

Configuration absence and software patch correctness are separate facts. The local patch proves the
workflow input boundary and static/parser behavior described above; it does not configure the
repository variable, execute Android CI, or establish that Android or all repository CI is green.

## Follow-up handoff: unused ignores and executable guard test

Date: 2026-09-29

Parent commit: `bd62e6fb3afc0ca66bb23881d97fa5db6c74d5d7`

The controller approved write ownership for exactly
`services/edge-hub/src/cloudctl_edge_hub/main.py` and
`services/control-api/src/cloudctl_api/fleet_live.py`, solely to remove their now-unused
`# type: ignore[import-untyped]` comments. No import, configuration, or runtime behavior changed.

Baseline-vs-worktree AST comparison for the two comment-only edits:

| Path | AST SHA-256 before/after | Nodes before/after | Equivalent |
|---|---|---:|---|
| `services/edge-hub/src/cloudctl_edge_hub/main.py` | `ed1cc59540192701f4f6119f778e181d219d83302bbd16d5c7b3fde2f0c7213a` | 1324 / 1324 | yes |
| `services/control-api/src/cloudctl_api/fleet_live.py` | `8690a521a69cbf3efec1c1d1f29484fc5a1a80d23c9004022893518a38e04037` | 5284 / 5284 | yes |

`tests/ops/test_ci_release_key.py` now executes the parsed first Android workflow step with
`/bin/bash -c`. It uses no real key and never invokes Gradle. Exact observed cases:

| Environment case | Guard return code | stdout | stderr | Sentinel leaked |
|---|---:|---|---|---|
| `CLOUDCTL_APP_UPDATE_PUBLIC_KEY` unset | 1 | GitHub error message requiring the repository variable | empty | no |
| `CLOUDCTL_APP_UPDATE_PUBLIC_KEY=""` | 1 | GitHub error message requiring the repository variable | empty | no |
| `CLOUDCTL_APP_UPDATE_PUBLIC_KEY=ci-public-key-sentinel-not-a-real-key` | 0 | empty | empty | no |

Follow-up commands and results:

| Command | Return code | Result |
|---|---:|---|
| AST comparison against `bd62e6f` for the two newly owned service files | 0 | 2/2 equivalent; hashes and node counts shown above. |
| `$VENV/bin/pytest -q tests/ops/test_ci_release_key.py` | 0 | 7 passed in 0.05s. |
| Parsed guard execution harness for unset, empty, and nonempty sentinel environments | 0 | Case return codes 1, 1, and 0; no sentinel disclosure. |
| `$VENV/bin/pytest -q tests/edge_hub_server_test.py tests/integration/test_fleet_live_session.py tests/integration/test_fleet_live_transport.py tests/ops/test_ci_release_key.py` | 0 | 64 passed in 8.03s. |
| `$VENV/bin/ruff format --check .` | 0 | 700 files already formatted. |
| `$VENV/bin/ruff check .` | 0 | All checks passed. |
| `$VENV/bin/mypy --config-file "$PWD/pyproject.toml"` with explicit worktree `MYPYPATH` | 0 | Success: no issues found in 162 source files. |
| `$VENV/bin/pyright --project "$PWD/pyproject.toml" --venvpath /Users/wangziheng/Desktop/01-主战场/LAMDA云控系统/cloudctl-source` | 0 | 0 errors, 0 warnings, 0 information. |
| `bash scripts/check-security-boundaries.sh` | 0 | Security boundary checks passed. |

No Gradle task, real key, GitHub configuration mutation, release, deploy, install, SSH, ADB, device,
publish, send, or production operation was used in this follow-up.
