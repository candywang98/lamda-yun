"""Store immutable task-bound order delivery receipts."""

import sqlalchemy as sa
from alembic import op

revision = "20260926_0035"
down_revision = "20260926_0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "order_delivery_receipt",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("task_id", sa.String(36), sa.ForeignKey("mobile_task.id"), nullable=False),
        sa.Column("device_id", sa.String(36), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("screen", sa.Integer(), nullable=False),
        sa.Column("payload_sha256", sa.String(64), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("conflict_code", sa.String(48)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "tenant_id", "task_id", "kind", "screen", name="uq_order_delivery_receipt"
        ),
        sa.CheckConstraint(
            "(kind = 'SCREEN' AND screen BETWEEN 1 AND 3) OR (kind = 'COMPLETE' AND screen = 0)",
            name="ck_order_delivery_kind_screen",
        ),
    )
    op.create_index("ix_order_delivery_receipt_tenant_id", "order_delivery_receipt", ["tenant_id"])
    op.create_index("ix_order_delivery_receipt_task_id", "order_delivery_receipt", ["task_id"])


def downgrade() -> None:
    op.drop_table("order_delivery_receipt")
