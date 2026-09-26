"""IM aggregation slice 1: threads and messages for companion push (pa-im/20260913.1)."""

import sqlalchemy as sa
from alembic import op

revision = "20260913_0017"
down_revision = "20260910_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "im_thread",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), nullable=False, index=True),
        sa.Column(
            "device_id", sa.String(36), sa.ForeignKey("device.id"), nullable=False, index=True
        ),
        sa.Column("platform", sa.String(32), nullable=False),
        sa.Column("peer_key", sa.String(128), nullable=False),
        sa.Column("peer_name", sa.String(128), nullable=False),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_direction", sa.String(8), nullable=False, server_default="IN"),
        sa.Column("unread_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "device_id", "peer_key", name="uq_im_thread_peer"),
        sa.CheckConstraint("last_direction IN ('IN', 'OUT')", name="ck_im_thread_direction"),
        sa.CheckConstraint("unread_count >= 0", name="ck_im_thread_unread"),
    )
    op.create_table(
        "im_message",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), nullable=False, index=True),
        sa.Column(
            "thread_id", sa.String(36), sa.ForeignKey("im_thread.id"), nullable=False, index=True
        ),
        sa.Column("direction", sa.String(8), nullable=False),
        sa.Column("content_type", sa.String(16), nullable=False, server_default="TEXT"),
        sa.Column("text_content", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("dedupe_key", sa.String(64), nullable=False, unique=True),
        sa.Column("reply_task_id", sa.String(36)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("direction IN ('IN', 'OUT')", name="ck_im_message_direction"),
        sa.CheckConstraint("content_type IN ('TEXT', 'SYSTEM')", name="ck_im_message_content_type"),
    )


def downgrade() -> None:
    op.drop_table("im_message")
    op.drop_table("im_thread")
