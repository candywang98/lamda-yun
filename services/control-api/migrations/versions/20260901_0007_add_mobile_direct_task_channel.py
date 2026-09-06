"""add mobile direct task channel

Revision ID: 20260901_0007
Revises: 20260831_0006
Create Date: 2026-09-01 17:05:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260901_0007"
down_revision: str | Sequence[str] | None = "20260831_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("device") as batch:
        batch.alter_column(
            "edge_id",
            existing_type=sa.String(length=36),
            nullable=True,
        )

    op.create_table(
        "mobile_enrollment",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("device_id", sa.String(length=36), nullable=False),
        sa.Column("code_digest", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["device_id"], ["device.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code_digest"),
    )
    op.create_index("ix_mobile_enrollment_tenant_id", "mobile_enrollment", ["tenant_id"])
    op.create_index("ix_mobile_enrollment_device_id", "mobile_enrollment", ["device_id"])

    op.create_table(
        "mobile_binding",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("device_id", sa.String(length=36), nullable=False),
        sa.Column("token_digest", sa.String(length=64), nullable=False),
        sa.Column("app_instance_id", sa.String(length=128), nullable=False),
        sa.Column("companion_version", sa.String(length=128), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["device_id"], ["device.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("device_id", "app_instance_id"),
        sa.UniqueConstraint("token_digest"),
    )
    op.create_index("ix_mobile_binding_tenant_id", "mobile_binding", ["tenant_id"])
    op.create_index("ix_mobile_binding_device_id", "mobile_binding", ["device_id"])

    op.create_table(
        "mobile_task",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("device_id", sa.String(length=36), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_sha256", sa.String(length=64), nullable=False),
        sa.Column("requested_by", sa.String(length=36), nullable=False),
        sa.Column("target_package", sa.String(length=255), nullable=False),
        sa.Column("steps", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("lease_id", sa.String(length=36), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("last_sequence", sa.Integer(), nullable=False),
        sa.Column("current_step", sa.Integer(), nullable=True),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["device_id"], ["device.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("lease_id"),
        sa.UniqueConstraint("tenant_id", "idempotency_key"),
    )
    op.create_index("ix_mobile_task_tenant_id", "mobile_task", ["tenant_id"])
    op.create_index("ix_mobile_task_device_id", "mobile_task", ["device_id"])
    op.create_index("ix_mobile_task_status", "mobile_task", ["status"])
    op.create_index(
        "uq_mobile_task_device_active",
        "mobile_task",
        ["device_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('CLAIMED', 'RUNNING')"),
        sqlite_where=sa.text("status IN ('CLAIMED', 'RUNNING')"),
    )

    op.create_table(
        "mobile_task_event",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("step_index", sa.Integer(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["mobile_task.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", "sequence"),
    )
    op.create_index("ix_mobile_task_event_tenant_id", "mobile_task_event", ["tenant_id"])
    op.create_index("ix_mobile_task_event_task_id", "mobile_task_event", ["task_id"])


def downgrade() -> None:
    op.drop_table("mobile_task_event")
    op.drop_table("mobile_task")
    op.drop_table("mobile_binding")
    op.drop_table("mobile_enrollment")
    with op.batch_alter_table("device") as batch:
        batch.alter_column(
            "edge_id",
            existing_type=sa.String(length=36),
            nullable=False,
        )
