# P0-004 evidence summary

- Task: PostgreSQL 基础模型与 Alembic
- Audited: 2026-08-31
- Software status: `implemented`
- Acceptance status: `pending`

## Proven evidence

- Implementation/configuration: `services/control-api/src/cloudctl_api/db.py`
- Implementation/configuration: `services/control-api/migrations/versions/20260831_0001_initial_control_plane_schema.py`
- Implementation/configuration: `services/control-api/migrations/versions/20260831_0002_add_operation_approvals_and_debug_.py`
- Implementation/configuration: `services/control-api/migrations/versions/20260831_0003_add_debug_session_fencing_lease.py`
- Test/runtime evidence: `tests/integration/test_control_api_migrations.py`
- Shared gate log: `artifacts/tasks/_verification-20260831/python-gates.log`

## Remaining acceptance gap

Migration tests pass, but the repository-wide format gate is not green and no production PostgreSQL migration run was captured.

