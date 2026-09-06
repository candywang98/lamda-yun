"""add debug session fencing lease

Revision ID: 20260831_0003
Revises: 20260831_0002
Create Date: 2026-08-31 10:56:17.241396
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260831_0003"
down_revision: str | Sequence[str] | None = "20260831_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("debug_session", sa.Column("lease_id", sa.String(length=36), nullable=True))
    op.add_column("debug_session", sa.Column("fencing_token", sa.Integer(), nullable=True))
    op.create_index(op.f("ix_debug_session_lease_id"), "debug_session", ["lease_id"], unique=True)
    op.execute(
        sa.text(
            """
            UPDATE debug_session
            SET status = 'REVOKED',
                relay_token_hash = NULL,
                relay_token_expires_at = NULL,
                revoked_at = COALESCE(revoked_at, created_at),
                revoke_reason = COALESCE(revoke_reason, 'migration: fencing lease required')
            WHERE status NOT IN ('REVOKED', 'EXPIRED')
            """
        )
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_debug_session_lease_id"), table_name="debug_session")
    op.drop_column("debug_session", "fencing_token")
    op.drop_column("debug_session", "lease_id")
