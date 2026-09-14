"""IM monitor per-device configuration (pa-im slice 2: platform selection + duty mode)."""

import sqlalchemy as sa
from alembic import op

revision = "20260914_0018"
down_revision = "20260913_0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "im_monitor_config",
        sa.Column("device_id", sa.String(36), sa.ForeignKey("device.id"), primary_key=True),
        sa.Column("tenant_id", sa.String(36), nullable=False, index=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("platforms", sa.JSON(), nullable=False),
        sa.Column("mode", sa.String(16), nullable=False, server_default="NOTIFICATION"),
        sa.Column("duty_start", sa.String(5), nullable=False, server_default="09:00"),
        sa.Column("duty_end", sa.String(5), nullable=False, server_default="23:00"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(36), nullable=False),
        sa.CheckConstraint("mode IN ('NOTIFICATION', 'DUTY')", name="ck_im_monitor_mode"),
    )


def downgrade() -> None:
    op.drop_table("im_monitor_config")
