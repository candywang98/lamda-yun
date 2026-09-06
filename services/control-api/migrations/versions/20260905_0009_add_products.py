"""add explicit product catalog tables"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260905_0009"
down_revision: str | Sequence[str] | None = "20260905_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "product",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("spu_code", sa.String(120), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("category", sa.String(160), nullable=False),
        sa.Column("price", sa.String(32), nullable=False),
        sa.Column("stock", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "spu_code"),
    )
    op.create_index("ix_product_tenant_id", "product", ["tenant_id"])
    op.create_index("ix_product_status", "product", ["status"])
    op.create_table(
        "product_media",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("product_id", sa.String(36), nullable=False),
        sa.Column("media_asset_id", sa.String(36), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["product.id"]),
        sa.ForeignKeyConstraint(["media_asset_id"], ["media_asset.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("product_id", "media_asset_id"),
    )
    op.create_index("ix_product_media_tenant_id", "product_media", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_product_media_tenant_id", table_name="product_media")
    op.drop_table("product_media")
    op.drop_index("ix_product_status", table_name="product")
    op.drop_index("ix_product_tenant_id", table_name="product")
    op.drop_table("product")
