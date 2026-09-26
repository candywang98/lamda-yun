"""fleet_listings fix: updated_at nullable (align table to the ORM).

Migration 0030 created ``updated_at NOT NULL`` on the three listing tables,
but the shared ``TimestampMixin`` only maps ``created_at`` — the ORM never
writes updated_at, so every production INSERT hit a NotNullViolation
(test environments create tables from ORM metadata, which is why the suite
stayed green). Align the tables to the ORM: drop the NOT NULL.

Column retention (nullable) keeps any external readers working; the
authoritative change signal is the snapshot-history append, not updated_at.
"""

import sqlalchemy as sa
from alembic import op

revision = "20260920_0032"
down_revision = "20260920_0031"
branch_labels = None
depends_on = None

_TABLES = ("fleet_listing", "fleet_listing_snapshot", "fleet_listing_screen")


def _set_nullable(nullable: bool) -> None:
    for table in _TABLES:
        if op.get_bind().dialect.name == "sqlite":
            with op.batch_alter_table(table) as batch:
                batch.alter_column(
                    "updated_at", existing_type=sa.DateTime(timezone=True), nullable=nullable
                )
        else:
            clause = "DROP NOT NULL" if nullable else "SET NOT NULL"
            op.execute(f"ALTER TABLE {table} ALTER COLUMN updated_at {clause}")


def upgrade() -> None:
    _set_nullable(True)


def downgrade() -> None:
    _set_nullable(False)
