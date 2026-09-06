"""add operation approvals and debug sessions

Revision ID: 20260831_0002
Revises: 20260831_0001
Create Date: 2026-08-31 09:39:04.907784
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260831_0002"
down_revision: str | Sequence[str] | None = "20260831_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("operation_task") as batch_op:
        batch_op.add_column(sa.Column("feature_id", sa.String(length=160), nullable=True))
        batch_op.add_column(sa.Column("context", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("approval_decision", sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column("approval_reason", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("approved_by", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True))
    op.execute(sa.text("UPDATE operation_task SET context = '{}' WHERE context IS NULL"))
    with op.batch_alter_table("operation_task") as batch_op:
        batch_op.alter_column("context", existing_type=sa.JSON(), nullable=False)
        batch_op.create_index(op.f("ix_operation_task_feature_id"), ["feature_id"], unique=False)

    op.create_table(
        "debug_session",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("edge_id", sa.String(length=36), nullable=False),
        sa.Column("device_id", sa.String(length=36), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("purpose", sa.String(length=1000), nullable=False),
        sa.Column("capabilities", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("launch_code_hash", sa.String(length=64), nullable=False),
        sa.Column("launch_code_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("relay_token_hash", sa.String(length=64), nullable=True),
        sa.Column("relay_token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("exchanged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stage", sa.String(length=80), nullable=True),
        sa.Column("last_event", sa.String(length=160), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("return_url", sa.String(length=1024), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by", sa.String(length=36), nullable=True),
        sa.Column("revoke_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("launch_code_hash"),
        sa.UniqueConstraint("relay_token_hash"),
    )
    op.create_index(
        op.f("ix_debug_session_device_id"), "debug_session", ["device_id"], unique=False
    )
    op.create_index(op.f("ix_debug_session_edge_id"), "debug_session", ["edge_id"], unique=False)
    op.create_index(op.f("ix_debug_session_status"), "debug_session", ["status"], unique=False)
    op.create_index(
        op.f("ix_debug_session_tenant_id"), "debug_session", ["tenant_id"], unique=False
    )
    op.create_table(
        "debug_evidence",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=80), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("object_ref", sa.String(length=1024), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["debug_session.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "sha256"),
    )
    op.create_index(
        op.f("ix_debug_evidence_session_id"),
        "debug_evidence",
        ["session_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_debug_evidence_tenant_id"),
        "debug_evidence",
        ["tenant_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_debug_evidence_tenant_id"), table_name="debug_evidence")
    op.drop_index(op.f("ix_debug_evidence_session_id"), table_name="debug_evidence")
    op.drop_table("debug_evidence")
    op.drop_index(op.f("ix_debug_session_tenant_id"), table_name="debug_session")
    op.drop_index(op.f("ix_debug_session_status"), table_name="debug_session")
    op.drop_index(op.f("ix_debug_session_edge_id"), table_name="debug_session")
    op.drop_index(op.f("ix_debug_session_device_id"), table_name="debug_session")
    op.drop_table("debug_session")
    with op.batch_alter_table("operation_task") as batch_op:
        batch_op.drop_index(op.f("ix_operation_task_feature_id"))
        batch_op.drop_column("decided_at")
        batch_op.drop_column("approved_by")
        batch_op.drop_column("approval_reason")
        batch_op.drop_column("approval_decision")
        batch_op.drop_column("context")
        batch_op.drop_column("feature_id")
