"""Xianyu order sync slice 1: read-only collected order snapshots.

Contract: contracts/phase1/order-sync-20260915.md (order-sync/20260915.1).
Companion collects order rows from the xianyu sold/bought list pages and
pushes them to POST /companion/v2/orders/batch; each row lands here exactly
once (unique natural key tenant+device+platform+order_key, first write wins,
snapshots are never rewritten in slice 1).

The table follows the im_thread tenant-isolation pattern: indexed tenant_id,
device_id foreign key. Check constraints are added through batch_alter_table
so the migration stays portable across PostgreSQL and SQLite (SQLite cannot
ALTER ADD CONSTRAINT directly), mirroring 20260915_0020.
"""

import sqlalchemy as sa
from alembic import op

revision = "20260915_0021"
down_revision = "20260915_0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "xianyu_order",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), nullable=False, index=True),
        sa.Column(
            "device_id", sa.String(36), sa.ForeignKey("device.id"), nullable=False, index=True
        ),
        sa.Column("platform", sa.String(32), nullable=False, server_default="xianyu"),
        sa.Column("direction", sa.String(8), nullable=False),
        sa.Column("order_key", sa.String(128), nullable=False),
        sa.Column("item_title", sa.String(256)),
        sa.Column("buyer_name", sa.String(128)),
        sa.Column("amount_cents", sa.Integer()),
        sa.Column("status_text", sa.String(64)),
        sa.Column("occurred_at", sa.DateTime(timezone=True)),
        sa.Column("raw", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "tenant_id",
            "device_id",
            "platform",
            "order_key",
            name="uq_xianyu_order_natural_key",
        ),
    )
    with op.batch_alter_table("xianyu_order") as batch:
        batch.create_check_constraint("ck_xianyu_order_platform", "platform IN ('xianyu')")
        batch.create_check_constraint(
            "ck_xianyu_order_direction", "direction IN ('SOLD', 'BOUGHT')"
        )
        batch.create_check_constraint(
            "ck_xianyu_order_amount", "amount_cents IS NULL OR amount_cents > 0"
        )


def downgrade() -> None:
    with op.batch_alter_table("xianyu_order") as batch:
        batch.drop_constraint("ck_xianyu_order_amount", type_="check")
        batch.drop_constraint("ck_xianyu_order_direction", type_="check")
        batch.drop_constraint("ck_xianyu_order_platform", type_="check")
    op.drop_table("xianyu_order")
