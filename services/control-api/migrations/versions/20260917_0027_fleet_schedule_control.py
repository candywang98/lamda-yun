"""fleet_schedule_control: F12 terminal cancel state for task schedules.

Task fleet-first-20260916.1 F12「立即/定时/周期调度与取消语义」. One new
additive table instead of new columns on ``task_schedule``: the legacy table
stays byte-compatible with the frozen task-schedule/v1 surface, while fleet
cancel gets an explicit terminal state with audit columns.

- ONE row per schedule (``schedule_id`` unique, FK task_schedule.id).
- ``status`` closed vocabulary ACTIVE | CANCELLED. CANCELLED is terminal:
  the fleet mint path refuses future triggers forever, while already-minted
  MobileTasks stay untouched — each is cancelled individually through the
  existing platform-tasks :cancel route (设备离线不自动迁移、任务不自动结案).
- ``cancelled_at`` / ``cancelled_by`` / ``cancel_reason`` carry the audit
  facts; the decision is additionally mirrored into an AuditEventRow by the
  service layer and into ``task_schedule.paused_reason`` so the legacy manual
  fire route stops firing too.

Downgrade drops the table: control rows are re-derivable state (a schedule
without a control row is ACTIVE by default), no task data lives here.
"""

import sqlalchemy as sa
from alembic import op

revision = "20260917_0027"
down_revision = "20260917_0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fleet_schedule_control",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        # No database-level FK: ``task_schedule`` lives in the legacy SQL
        # migration path (006_task_schedules.sql), not the alembic chain, so a
        # FK here would break fresh alembic-only databases (and the postgres
        # upgrade test). Referential integrity is enforced at the service
        # layer, which always loads the TaskScheduleRow first.
        sa.Column("schedule_id", sa.String(36), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="ACTIVE"),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_by", sa.String(64), nullable=True),
        sa.Column("cancel_reason", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        # Inline (not a separate add_constraint): SQLite cannot ALTER
        # constraints, so the downgrade stays a plain drop_table.
        sa.UniqueConstraint("schedule_id", name="uq_fleet_schedule_control_schedule_id"),
    )
    op.create_index("ix_fleet_schedule_control_tenant_id", "fleet_schedule_control", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_fleet_schedule_control_tenant_id", table_name="fleet_schedule_control")
    op.drop_table("fleet_schedule_control")
