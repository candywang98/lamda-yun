"""fleet_listings: P43/P44 listing identity + change history + page guard.

Three tables for xy-tasks-24 采集宝贝信息 (fleet-first-20260916.1):

- ``fleet_listing``          — one row per (tenant, device, platform,
  item_key): composite natural key identity, mutable latest snapshot,
  content hash and snapshot counter.
- ``fleet_listing_snapshot`` — append-only history, inserted only when the
  parsed content hash changes (宝贝价格/状态变化可查询).
- ``fleet_listing_screen``   — (tenant, device, run_key, screen) unique page
  guard so an offline replay never double-counts.

Downgrade drops all three: collection state is re-derivable from the device
by re-running the read-only collector; no business ledger lives here.
"""

import sqlalchemy as sa
from alembic import op

revision = "20260920_0030"
down_revision = "20260917_0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fleet_listing",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), nullable=False, index=True),
        sa.Column(
            "device_id", sa.String(36), sa.ForeignKey("device.id"), nullable=False, index=True
        ),
        sa.Column("platform", sa.String(16), nullable=False, server_default="xianyu"),
        sa.Column("item_key", sa.String(128), nullable=False),
        sa.Column("dedupe_marker", sa.String(16), nullable=False, server_default="MISSING_ID"),
        sa.Column("title", sa.String(64)),
        sa.Column("price_cents", sa.Integer()),
        sa.Column("price_text", sa.String(32)),
        sa.Column("status_text", sa.String(64)),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("snapshot_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "tenant_id",
            "device_id",
            "platform",
            "item_key",
            name="uq_fleet_listing_identity",
        ),
        sa.CheckConstraint(
            "price_cents is null or price_cents >= 0", name="ck_fleet_listing_price"
        ),
    )
    op.create_table(
        "fleet_listing_snapshot",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), nullable=False, index=True),
        sa.Column("device_id", sa.String(36), nullable=False, index=True),
        sa.Column("item_key", sa.String(128), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("snapshot_json", sa.String(4096), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "fleet_listing_screen",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), nullable=False, index=True),
        sa.Column("device_id", sa.String(36), nullable=False, index=True),
        sa.Column("platform", sa.String(16), nullable=False, server_default="xianyu"),
        sa.Column("run_key", sa.String(64), nullable=False),
        sa.Column("screen", sa.Integer(), nullable=False),
        sa.Column("rows_seen", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("new_keys", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_keys", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duplicates", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("partial_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("empty_page", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("collected_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "tenant_id", "device_id", "run_key", "screen", name="uq_fleet_listing_screen"
        ),
    )


def downgrade() -> None:
    op.drop_table("fleet_listing_screen")
    op.drop_table("fleet_listing_snapshot")
    op.drop_table("fleet_listing")
