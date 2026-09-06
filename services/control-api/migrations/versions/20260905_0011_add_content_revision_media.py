"""add indexed content revision media references"""

import uuid

import sqlalchemy as sa
from alembic import op

revision = "20260905_0011"
down_revision = "20260905_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "content_revision_media",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column(
            "content_revision_id",
            sa.String(36),
            sa.ForeignKey("content_revision.id"),
            nullable=False,
        ),
        sa.Column("content_id", sa.String(36), sa.ForeignKey("content_item.id"), nullable=False),
        sa.Column("media_asset_id", sa.String(36), sa.ForeignKey("media_asset.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("content_revision_id", "media_asset_id"),
    )
    op.create_index("ix_content_revision_media_tenant_id", "content_revision_media", ["tenant_id"])
    op.create_index(
        "ix_content_revision_media_media_asset_id", "content_revision_media", ["media_asset_id"]
    )
    op.create_index(
        "ix_content_revision_media_content_revision_id",
        "content_revision_media",
        ["content_revision_id"],
    )
    op.create_index(
        "ix_content_revision_media_content_id", "content_revision_media", ["content_id"]
    )
    connection = op.get_bind()
    metadata = sa.MetaData()
    revisions = sa.Table("content_revision", metadata, autoload_with=connection)
    assets = sa.Table("media_asset", metadata, autoload_with=connection)
    references = sa.Table("content_revision_media", metadata, autoload_with=connection)
    last_id = ""
    while True:
        batch = (
            connection.execute(
                sa.select(revisions)
                .where(revisions.c.id > last_id)
                .order_by(revisions.c.id)
                .limit(500)
            )
            .mappings()
            .all()
        )
        if not batch:
            break
        for row in batch:
            payload = row["payload"]
            ids = payload.get("mediaAssetIds") if isinstance(payload, dict) else None
            if ids is None:
                continue
            if not isinstance(ids, list) or any(not isinstance(value, str) for value in ids):
                raise RuntimeError(f"invalid legacy media references in revision {row['id']}")
            for asset_id in dict.fromkeys(ids):
                exists = connection.scalar(
                    sa.select(assets.c.id).where(
                        assets.c.id == asset_id, assets.c.tenant_id == row["tenant_id"]
                    )
                )
                if exists is None:
                    raise RuntimeError(f"invalid legacy media ownership in revision {row['id']}")
                connection.execute(
                    references.insert().values(
                        id=str(uuid.uuid4()),
                        tenant_id=row["tenant_id"],
                        content_revision_id=row["id"],
                        content_id=row["content_id"],
                        media_asset_id=asset_id,
                        created_at=row["created_at"],
                    )
                )
        last_id = batch[-1]["id"]


def downgrade() -> None:
    op.drop_index("ix_content_revision_media_content_id", table_name="content_revision_media")
    op.drop_index(
        "ix_content_revision_media_content_revision_id", table_name="content_revision_media"
    )
    op.drop_index("ix_content_revision_media_media_asset_id", table_name="content_revision_media")
    op.drop_index("ix_content_revision_media_tenant_id", table_name="content_revision_media")
    op.drop_table("content_revision_media")
