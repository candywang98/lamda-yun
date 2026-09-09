"""Persist claim recipe pins and serialized per-command deployment history.

Revision ID: 20260909_0015
Revises: 20260908_0014
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260909_0015"
down_revision: str | Sequence[str] | None = "20260908_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("mobile_task", sa.Column("recipe_pin", sa.JSON(), nullable=True))
    op.add_column(
        "recipe_device_deployment",
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Old rows did not record mutation time. Persist the last known timestamp;
    # do not manufacture timestamps when returning legacy history to clients.
    op.execute("UPDATE recipe_device_deployment SET updated_at = created_at")
    # Preserve every historical row. Deterministically retire duplicate active
    # rows from the previous schema before enforcing the new invariant.
    op.execute("""
        UPDATE recipe_device_deployment SET status = 'REVOKED', updated_at = CURRENT_TIMESTAMP
        WHERE id IN (
            SELECT id FROM (
                SELECT id, ROW_NUMBER() OVER (
                    PARTITION BY tenant_id, device_id, command_type
                    ORDER BY created_at DESC, id DESC
                ) AS position
                FROM recipe_device_deployment WHERE status = 'PUBLISHED'
            ) AS ranked WHERE position > 1
        )
    """)
    old_key_name = (
        next(
            (
                item["name"]
                for item in sa.inspect(op.get_bind()).get_unique_constraints(
                    "recipe_device_deployment"
                )
                if item["column_names"] == ["tenant_id", "device_id", "idempotency_key"]
            ),
            None,
        )
        or "uq_recipe_device_deployment_tenant_id_device_id_idempotency_key"
    )
    with op.batch_alter_table(
        "recipe_device_deployment",
        naming_convention={
            "uq": "uq_%(table_name)s_%(column_0_name)s_%(column_1_name)s_%(column_2_name)s"
        },
    ) as batch:
        batch.drop_constraint(old_key_name, type_="unique")
        batch.create_unique_constraint(
            "uq_recipe_deploy_command_key",
            ["tenant_id", "device_id", "command_type", "idempotency_key"],
        )
        batch.alter_column("updated_at", existing_type=sa.DateTime(timezone=True), nullable=False)
    op.create_index(
        "uq_recipe_deploy_published",
        "recipe_device_deployment",
        ["tenant_id", "device_id", "command_type"],
        unique=True,
        postgresql_where=sa.text("status = 'PUBLISHED'"),
        sqlite_where=sa.text("status = 'PUBLISHED'"),
    )
    op.create_table(
        "recipe_deployment_action",
        sa.Column("tenant_id", sa.String(36), primary_key=True),
        sa.Column("idempotency_key", sa.String(128), primary_key=True),
        sa.Column("request_sha256", sa.String(64), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column(
            "version_id",
            sa.String(36),
            sa.ForeignKey("automation_package_version.id"),
            nullable=False,
        ),
        sa.Column("actor_id", sa.String(36), nullable=False),
        sa.Column("response", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("recipe_deployment_action")
    op.drop_index("uq_recipe_deploy_published", table_name="recipe_device_deployment")
    # Older schema cannot represent multi-command keys. Retain every deployment
    # and disambiguate keys only for duplicate legacy tuples using the row UUID.
    op.execute("""
        UPDATE recipe_device_deployment SET idempotency_key = id
        WHERE id IN (
            SELECT id FROM (
                SELECT id, ROW_NUMBER() OVER (
                    PARTITION BY tenant_id, device_id, idempotency_key ORDER BY command_type, id
                ) AS position FROM recipe_device_deployment
            ) AS ranked WHERE position > 1
        )
    """)
    with op.batch_alter_table("recipe_device_deployment") as batch:
        batch.drop_constraint("uq_recipe_deploy_command_key", type_="unique")
        batch.create_unique_constraint(
            "uq_recipe_device_deployment_tenant_id_device_id_idempotency_key",
            ["tenant_id", "device_id", "idempotency_key"],
        )
        batch.drop_column("updated_at")
    op.drop_column("mobile_task", "recipe_pin")
