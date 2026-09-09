"""store per-device signed recipe deployments"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260908_0014"
down_revision: str | Sequence[str] | None = "20260906_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "recipe_device_deployment",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("version_id", sa.String(length=36), nullable=False),
        sa.Column("device_id", sa.String(length=36), nullable=False),
        sa.Column("command_type", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("previous_version_id", sa.String(length=36), nullable=True),
        sa.Column("published_by", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["version_id"], ["automation_package_version.id"]),
        sa.ForeignKeyConstraint(["device_id"], ["device.id"]),
        sa.UniqueConstraint("tenant_id", "device_id", "idempotency_key"),
        sa.CheckConstraint("status IN ('PUBLISHED','REVOKED')", name="recipe_deployment_status"),
    )
    op.create_index(
        "ix_recipe_deploy_active",
        "recipe_device_deployment",
        ["tenant_id", "device_id", "command_type", "status"],
    )
    op.create_index(
        "ix_recipe_device_deployment_tenant_id",
        "recipe_device_deployment",
        ["tenant_id"],
    )
    op.create_index(
        "ix_recipe_device_deployment_version_id",
        "recipe_device_deployment",
        ["version_id"],
    )
    op.create_index(
        "ix_recipe_device_deployment_device_id",
        "recipe_device_deployment",
        ["device_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_recipe_device_deployment_device_id", table_name="recipe_device_deployment")
    op.drop_index("ix_recipe_device_deployment_version_id", table_name="recipe_device_deployment")
    op.drop_index("ix_recipe_device_deployment_tenant_id", table_name="recipe_device_deployment")
    op.drop_index("ix_recipe_deploy_active", table_name="recipe_device_deployment")
    op.drop_table("recipe_device_deployment")
