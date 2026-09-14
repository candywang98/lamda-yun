"""IM reply delivery state: mark OUT messages with task-bound delivery truth.

Real-device acceptance showed that a reply task can fail safely after the OUT
im_message row was already written (INPUT_IME_REQUIRED / STEP_TIMEOUT with zero
side effects), leaving an unsent message indistinguishable from a delivered
one. Adds im_message.delivery_state (PENDING/DELIVERED/FAILED):

- reply dispatch writes PENDING;
- task terminal SUCCEEDED -> DELIVERED, FAILED/CANCELLED/EXPIRED -> FAILED;
- existing rows are backfilled conservatively as DELIVERED: pre-migration
  history is not rewritten, old data is treated as delivered.

batch_alter_table keeps the CHECK constraint portable across PostgreSQL and
SQLite (SQLite cannot ALTER ADD CONSTRAINT directly).
"""

import sqlalchemy as sa
from alembic import op

revision = "20260915_0020"
down_revision = "20260915_0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("im_message") as batch:
        batch.add_column(
            sa.Column("delivery_state", sa.String(16), nullable=False, server_default="DELIVERED")
        )
        batch.create_check_constraint(
            "ck_im_message_delivery_state",
            "delivery_state IN ('PENDING', 'DELIVERED', 'FAILED')",
        )
        # The direction/content_type checks already exist from 20260913_0017 on
        # PostgreSQL; only the settlement lookup index is new here, keeping
        # migrated schemas in parity with the ORM model (db.py ImMessageRow).
        batch.create_index("ix_im_message_reply_task_id", ["reply_task_id"])


def downgrade() -> None:
    with op.batch_alter_table("im_message") as batch:
        batch.drop_index("ix_im_message_reply_task_id")
        batch.drop_constraint("ck_im_message_delivery_state", type_="check")
        batch.drop_column("delivery_state")
