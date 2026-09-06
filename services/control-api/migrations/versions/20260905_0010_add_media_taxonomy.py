"""add media tags and groups"""

import sqlalchemy as sa
from alembic import op

revision = "20260905_0010"
down_revision = "20260905_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "media_tag",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("media_asset_id", sa.String(36), sa.ForeignKey("media_asset.id"), nullable=False),
        sa.Column("tag", sa.String(80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("media_asset_id", "tag"),
    )
    op.create_index("ix_media_tag_tenant_id", "media_tag", ["tenant_id"])
    op.create_table(
        "media_group",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "name"),
    )
    op.create_index("ix_media_group_tenant_id", "media_group", ["tenant_id"])
    op.create_table(
        "media_group_membership",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("group_id", sa.String(36), sa.ForeignKey("media_group.id"), nullable=False),
        sa.Column("media_asset_id", sa.String(36), sa.ForeignKey("media_asset.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("group_id", "media_asset_id"),
    )
    op.create_index("ix_media_group_membership_tenant_id", "media_group_membership", ["tenant_id"])
    op.create_index("ix_media_tag_media_asset_id", "media_tag", ["media_asset_id"])
    op.create_index("ix_media_group_membership_group_id", "media_group_membership", ["group_id"])
    op.create_index(
        "ix_media_group_membership_media_asset_id", "media_group_membership", ["media_asset_id"]
    )


def downgrade() -> None:
    op.drop_table("media_group_membership")
    op.drop_table("media_group")
    op.drop_table("media_tag")
