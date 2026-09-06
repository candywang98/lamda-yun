"""add tenant operation feature configuration drafts

Revision ID: 20260831_0006
Revises: 20260831_0005
Create Date: 2026-08-31 18:20:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260831_0006"
down_revision: str | Sequence[str] | None = "20260831_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "operation_feature_config_draft",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("feature_id", sa.String(length=160), nullable=False),
        sa.Column("configuration_json", sa.JSON(), nullable=False),
        sa.Column("configuration_sha256", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_by", sa.String(length=36), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "version >= 1",
            name="ck_operation_feature_config_draft_version",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "feature_id",
            name="uq_operation_feature_config_draft_tenant_feature",
        ),
    )
    op.create_index(
        "ix_operation_feature_config_draft_tenant_id",
        "operation_feature_config_draft",
        ["tenant_id"],
    )
    op.create_index(
        "ix_operation_feature_config_draft_feature_id",
        "operation_feature_config_draft",
        ["feature_id"],
    )


def downgrade() -> None:
    op.drop_table("operation_feature_config_draft")
