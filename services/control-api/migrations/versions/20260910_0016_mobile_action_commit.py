"""Persist the Companion controlled-action ledger independently of publish targets."""

import sqlalchemy as sa
from alembic import op

revision = "20260910_0016"
down_revision = "20260909_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mobile_action_commit",
        sa.Column("action_key", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("task_id", sa.String(36), sa.ForeignKey("mobile_task.id"), nullable=False),
        sa.Column("device_id", sa.String(36), nullable=False),
        sa.Column("account_id", sa.String(36), nullable=False),
        sa.Column("binding_version", sa.Integer(), nullable=False),
        sa.Column("recipe_version_id", sa.String(128), nullable=False),
        sa.Column("recipe_sha256", sa.String(64), nullable=False),
        sa.Column("snapshot_sha256", sa.String(64), nullable=False),
        sa.Column("action_id", sa.String(128), nullable=False),
        sa.Column("parameter_hash", sa.String(64), nullable=False),
        sa.Column("lease_id", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("before_evidence", sa.String(500), nullable=False),
        sa.Column("reported_evidence", sa.String(500)),
        sa.Column("resolution_revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("resolution_evidence", sa.Text()),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("task_id", "action_id", name="uq_mobile_action_task_state"),
        sa.CheckConstraint(
            "status IN ('INTENT', 'APPLIED', 'UNKNOWN', 'NOT_SUBMITTED')",
            name="ck_mobile_action_status",
        ),
        sa.CheckConstraint("resolution_revision >= 0", name="ck_mobile_action_revision"),
    )


def downgrade() -> None:
    op.drop_table("mobile_action_commit")
