# Narrow deadline review follow-up

- Preflight recorded locally: `2026-09-30T00:05:54.134968+08:00`.
- Validation completion recorded locally: `2026-09-30T00:09:15+08:00`.
- Parent: `14c95eb6dfd7c17fdbbad97ea48bc6d12cdaa3c4`.
- Branch: `agent/astra-fleet-ci-evidence-20260929`.
- Only code delta: `test_runner_records_honest_exit_and_refuses_directory_reuse`
  in `tests/load/fleet/test_ci_diagnostics.py`.

```python
deadline_seconds = 0.01 if outcome == "timeout" else ci_diagnostics.DEADLINE_SECONDS
exit_code = await diagnose(directory, deadline_seconds=deadline_seconds)
```

The intentional timeout still uses 10 ms. Success/assertion cases now use the
existing 180-second default, avoiding an unrelated deadline on thread startup.
The target and every assertion are unchanged. Runner default, production,
workflow and original benchmark p95 < 5.0 are unchanged.

## Validation

All exits 0. Log prefix: `deadline-review-20260930-`.

| Check | Result | Log suffix |
| --- | --- | --- |
| Diagnostic tests and both CI ops files | 49 passed, 8.20s | `tests.log` |
| Scoped Ruff | All checks passed | `ruff.log` |
| Scoped format | 3 files already formatted | `format.log` |
| Relevant mypy | 2 source files clean | `mypy.log` |
| Relevant Pyright | 0 errors/warnings | `pyright.log` |

Commands, executed from the isolated worktree:

```bash
../cloudctl-source/.venv/bin/python -m pytest -q -rs -p no:cacheprovider \
  -W error::RuntimeWarning -W error::ResourceWarning \
  -W error::pytest.PytestUnraisableExceptionWarning \
  tests/load/fleet/test_ci_diagnostics.py \
  tests/ops/test_ci_python_portability.py tests/ops/test_ci_release_key.py
../cloudctl-source/.venv/bin/ruff check \
  tests/load/fleet/test_ci_diagnostics.py \
  tests/ops/test_ci_python_portability.py tests/ops/test_ci_release_key.py
../cloudctl-source/.venv/bin/ruff format --check \
  tests/load/fleet/test_ci_diagnostics.py \
  tests/ops/test_ci_python_portability.py tests/ops/test_ci_release_key.py
env -u MYPYPATH -u PYTHONPATH ../cloudctl-source/.venv/bin/mypy \
  --no-incremental --cache-dir=/dev/null \
  tests/load/fleet/ci_diagnostics.py tests/load/fleet/test_ci_diagnostics.py
../cloudctl-source/.venv/bin/pyright --venvpath ../cloudctl-source \
  tests/load/fleet/ci_diagnostics.py tests/load/fleet/test_ci_diagnostics.py
```

Execution handles 5101, 39246 and 51676 are terminal, exit 0; none active.
No full suite, ABBA repetition, GitHub observation or benchmark rerun was
performed. Original 38 untracked worktree files remain protected.

## Recovery fact, no retry

The earlier main preflight failure was self-induced: shell stdout redirection
created `preflight.json` before the script checked for an empty directory.
It was NOT evidence of repository drift, and occurred before Git preflight.
No main command was retried during this follow-up. Main integration/push remain held.

The external files remain unchanged:

```text
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  preflight.json (0 bytes)
0b3c95b7d9734f95ffb9eeaba27226fc21cb3a9f0c91b5941c44cfb82d228091  preflight-failure.json
```

Their directory is
`/Users/wangziheng/CloudCtlExternal/acceptance/20260929-fleet-ci-evidence-main/`.
Any future authorized correction must validate Git state first, then serialize
to a NEW unused filename with exclusive creation. It must not require an
existing evidence directory to be empty or delete/overwrite prior evidence.
