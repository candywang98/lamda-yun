"""fleet_order_page / fleet_order_checkpoint: O10 pagination + checkpoint bookkeeping.

Task fleet-first-20260916.1 O10 (订单分页、去重、断点和历史切片). Two new
tables, disjoint from the accepted order-sync slices:

- ``fleet_order_page``       — one page-summary row per collected screen.
  ``(tenant_id, device_id, run_key, screen)`` unique: an offline replay of
  the same screen stores exactly one page (断网重传不重复计数). Empty/partial
  flags and new/overlap counters feed the history collection-window and
  missing-page annotations.
- ``fleet_order_checkpoint`` — ONE active resume point per
  ``(tenant_id, device_id, platform, direction)``. Binds account_key +
  schema_version + current run_key + last_screen: a different account
  (设备 A 的订单不归 B 账号), a different schema version, or a silent screen
  skip is refused with 409; replays of seen screens stay idempotent.

Order snapshots themselves stay in the existing ``xianyu_order`` table
(the O10 fleet layer upserts status changes there and marks degraded
dedupe keys inside ``raw``); the downgrade simply drops both bookkeeping
tables because page/checkpoint rows are re-derivable from the companion
replay + the order snapshots.
"""

import sqlalchemy as sa
from alembic import op

revision = "20260917_0026"
down_revision = "20260917_0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fleet_order_page",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("device_id", sa.String(36), nullable=False),
        sa.Column("platform", sa.String(32), nullable=False),
        sa.Column("direction", sa.String(8), nullable=False),
        sa.Column("account_key", sa.String(128), nullable=False),
        sa.Column("run_key", sa.String(128), nullable=False),
        sa.Column("screen", sa.Integer(), nullable=False),
        sa.Column("rows_seen", sa.Integer(), nullable=False),
        sa.Column("new_keys", sa.Integer(), nullable=False),
        sa.Column("updated_keys", sa.Integer(), nullable=False),
        sa.Column("overlap", sa.Integer(), nullable=False),
        sa.Column("partial_rows", sa.Integer(), nullable=False),
        sa.Column("empty_page", sa.Boolean(), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["device_id"], ["device.id"]),
        sa.UniqueConstraint(
            "tenant_id", "device_id", "run_key", "screen",
            name="uq_fleet_order_page_screen",
        ),
        sa.CheckConstraint("platform IN ('xianyu')", name="ck_fleet_order_page_platform"),
        sa.CheckConstraint("direction IN ('SOLD', 'BOUGHT')", name="ck_fleet_order_page_direction"),
        sa.CheckConstraint("screen >= 1", name="ck_fleet_order_page_screen_positive"),
        sa.CheckConstraint(
            "rows_seen >= 0 AND new_keys >= 0 AND overlap >= 0",
            name="ck_fleet_order_page_counts",
        ),
    )
    op.create_index("ix_fleet_order_page_tenant_id", "fleet_order_page", ["tenant_id"])
    op.create_index("ix_fleet_order_page_device_id", "fleet_order_page", ["device_id"])
    op.create_index("ix_fleet_order_page_run_key", "fleet_order_page", ["run_key"])

    op.create_table(
        "fleet_order_checkpoint",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("device_id", sa.String(36), nullable=False),
        sa.Column("platform", sa.String(32), nullable=False),
        sa.Column("direction", sa.String(8), nullable=False),
        sa.Column("account_key", sa.String(128), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("run_key", sa.String(128), nullable=False),
        sa.Column("last_screen", sa.Integer(), nullable=False),
        sa.Column("seen_keys", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["device_id"], ["device.id"]),
        sa.UniqueConstraint(
            "tenant_id", "device_id", "platform", "direction",
            name="uq_fleet_order_checkpoint_binding",
        ),
        sa.CheckConstraint("platform IN ('xianyu')", name="ck_fleet_order_checkpoint_platform"),
        sa.CheckConstraint(
            "direction IN ('SOLD', 'BOUGHT')", name="ck_fleet_order_checkpoint_direction"
        ),
        sa.CheckConstraint("schema_version >= 1", name="ck_fleet_order_checkpoint_version"),
        sa.CheckConstraint(
            "last_screen >= 0 AND seen_keys >= 0", name="ck_fleet_order_checkpoint_counts"
        ),
    )
    op.create_index("ix_fleet_order_checkpoint_tenant_id", "fleet_order_checkpoint", ["tenant_id"])
    op.create_index("ix_fleet_order_checkpoint_device_id", "fleet_order_checkpoint", ["device_id"])


def downgrade() -> None:
    op.drop_index("ix_fleet_order_checkpoint_device_id", table_name="fleet_order_checkpoint")
    op.drop_index("ix_fleet_order_checkpoint_tenant_id", table_name="fleet_order_checkpoint")
    op.drop_table("fleet_order_checkpoint")
    op.drop_index("ix_fleet_order_page_run_key", table_name="fleet_order_page")
    op.drop_index("ix_fleet_order_page_device_id", table_name="fleet_order_page")
    op.drop_index("ix_fleet_order_page_tenant_id", table_name="fleet_order_page")
    op.drop_table("fleet_order_page")
