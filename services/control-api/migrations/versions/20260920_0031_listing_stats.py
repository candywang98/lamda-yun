"""fleet_listings stat columns: exposure/views/wants per card (P43/P44).

The 「我发布的」 card content-desc carries 曝光N / 浏览N / 想要N as separate
lines (verified on-device 2026-09-20, OnePlus 9R). These are mutable metrics:
they participate in the content hash (a metric change appends a snapshot row)
and are exposed on the listing view for the 宝贝流量变化 report.
"""

import sqlalchemy as sa
from alembic import op

revision = "20260920_0031"
down_revision = "20260920_0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("fleet_listing") as batch:
        batch.add_column(sa.Column("exposure_count", sa.Integer()))
        batch.add_column(sa.Column("views_count", sa.Integer()))
        batch.add_column(sa.Column("wants_count", sa.Integer()))


def downgrade() -> None:
    with op.batch_alter_table("fleet_listing") as batch:
        batch.drop_column("wants_count")
        batch.drop_column("views_count")
        batch.drop_column("exposure_count")
