"""link publish plans to canonical products"""

import sqlalchemy as sa
from alembic import op

revision = "20260905_0012"
down_revision = "20260905_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("publish_plan", recreate="always") as batch:
            batch.add_column(sa.Column("product_id", sa.String(36), nullable=True))
            batch.create_foreign_key(
                "fk_publish_plan_product_id", "product", ["product_id"], ["id"]
            )
    else:
        op.add_column("publish_plan", sa.Column("product_id", sa.String(36), nullable=True))
        op.create_foreign_key(
            "fk_publish_plan_product_id", "publish_plan", "product", ["product_id"], ["id"]
        )
    op.create_index("ix_publish_plan_product_id", "publish_plan", ["product_id"])


def downgrade() -> None:
    op.drop_index("ix_publish_plan_product_id", table_name="publish_plan")
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("publish_plan", recreate="always") as batch:
            batch.drop_constraint("fk_publish_plan_product_id", type_="foreignkey")
            batch.drop_column("product_id")
    else:
        op.drop_constraint("fk_publish_plan_product_id", "publish_plan", type_="foreignkey")
        op.drop_column("publish_plan", "product_id")
