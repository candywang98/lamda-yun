"""add companion device preview frames

Revision ID: 20260905_0008
Revises: 20260901_0007
Create Date: 2026-09-05 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260905_0008"
down_revision: str | Sequence[str] | None = "20260901_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "device_preview",
        sa.Column("device_id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=True),
        sa.Column("session_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("requested_by", sa.String(length=36), nullable=True),
        sa.Column("capture_interval_ms", sa.Integer(), nullable=False),
        sa.Column("frame_session_id", sa.String(length=36), nullable=True),
        sa.Column("content_type", sa.String(length=64), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("image_bytes", sa.LargeBinary(), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["device_id"], ["device.id"]),
        sa.PrimaryKeyConstraint("device_id"),
    )
    op.create_index("ix_device_preview_tenant_id", "device_preview", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_device_preview_tenant_id", table_name="device_preview")
    op.drop_table("device_preview")
