# P14 preflight

## Completed

- Source/plan checkpoint `8143664854b479c5759a292daa3d4f8415e60025` pushed to `https://github.com/candywang98/lamda-yun`, remote main SHA independently checked.
- Exact copies of three plan workbooks and three handoff/implementation documents under `docs/project-plans/`; SHA-256 manifest verified against originals.
- Local runtime databases, laboratory enrollment/config files, build caches and archive traces removed from current Git tracking while preserving local copies. New raw task artifacts excluded; Markdown reports retained. Existing Git history was not rewritten.
- Credential-pattern scan of new/changed text and workbook cells found no token/private-key matches. Two broad assignment matches were code constants/test redaction fixtures.
- Frozen `recipe-version/20260909.1` at `contracts/phase1/p14-recipe-version-contract.md`, baseline `364c264e21dfcc0464a8537b95f2445af9f35fcf`.
- Isolated worktrees for `agent/p14-api-version-pin`, `agent/p14-android-lifecycle`, `agent/p14-web-t041` all created from that baseline. Root works on `integration/p14-20260909`.

## Baseline checks

Command: `.venv/bin/python -m pytest -q tests/integration/test_backend_control_api.py tests/integration/test_mobile_task_api.py tests/integration/test_control_api_migrations.py tests/unit/test_command_factory.py tests/unit/test_command_v1.py tests/unit/test_recipe_package.py`

Result: **54 passed in 16.41s**. Captured locally at `/tmp/lamda-p14-baseline-tests.log`. This validates the starting software baseline, not the pending lifecycle implementation.

ADB serial `b0644fb5`: online/authorized; OnePlus 9R LE2100; Companion 0.1.0 versionCode 1 installed; Accessibility service enabled; CompanionSyncService foreground and started. Public API `/health/live` returned HTTP 200 `status=ok`; SSH batch connection succeeded. No task, deployment, enrollment or foreground-app state was changed by these checks.

## Delegation

Initial built-in workers failed before source edits due to provider configuration (401 and unsupported developer role). A dedicated user agent pins the working parent provider/model (`sub-geren/gpt-6-astra`), with max thinking, and three replacement workers were dispatched without waiting between lanes. Root retains shared contracts, device, release, deploy and merge ownership. Completion is subject to tests and integration; P14 is not yet accepted.
