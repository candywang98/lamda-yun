# P14-CONTROL-VERSION delivery

Baseline: `364c264e21dfcc0464a8537b95f2445af9f35fcf`
Branch: `agent/p14-api-version-pin`
Contract: `recipe-version/20260909.1`

Implemented tenant-scoped catalog and deployment metadata; explicit idempotent publish/revoke/rollback actions; expected-current-version/history checks; sorted device transaction locks and database partial unique active index per device/command; persistent first-claim recipe pins including builtins; authenticated pinned historical downloads; audit and migration `20260909_0015`.

Root review additionally blocks claim while RECONCILING and refuses silently choosing a new recipe for pre-migration attempted tasks with no saved recipe pin. Such tasks require reconciliation. New SQLite and PostgreSQL tests assert no attempt increment or version drift.

## Root verification

Command (PATH includes `/opt/homebrew/opt/postgresql@16/bin`):

```
python -m pytest -q tests/integration/test_p14_recipe_versions.py tests/integration/test_backend_control_api.py tests/integration/test_mobile_task_api.py tests/integration/test_control_api_migrations.py tests/integration/test_platform_tasks.py tests/unit/test_command_factory.py tests/unit/test_command_v1.py tests/unit/test_recipe_package.py
```

Exit 0, **86 passed in 17.64s**, no skips. Uses disposable test-owned PostgreSQL clusters and SQLite, no production database. Log `/tmp/lamda-p14-control-verified.log`.

Ruff new migration/test files: exit 0, all checks passed. Full changed backend files have 10 inherited lint findings versus 13 at baseline; no new diagnostic kinds/locations. Existing formatting/Body-default lint debt is not represented as a clean whole-repository lint pass.

Worker time limit ended before commit; Root inspected and verified the terminal worktree and creates the reviewed commit. Device/deployment/browser integration remains Root-owned, no hardware acceptance claimed here.
