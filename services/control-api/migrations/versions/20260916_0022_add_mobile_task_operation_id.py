"""mobile_task.operation_id: persist the field-map catalog identity (K03 D1).

Contract: contracts/parallel/K03/task-schedule-v1.md (task-schedule/v1@20260916.1,
FROZEN 20260916.1, ruling D1). The identity chain is

    operationId (field-map.json)
      --PRODUCTION_ALIASES--> commandType
      --> MobileTaskRow(id, command_type, operation_id)
      --> taskId (CommandV1)
      --> events (Unique(task_id, sequence))
      --> batch_id

so the operator task list and event-driven audit lookups can resolve a task
back to its catalog operation without re-deriving it from parameters.

The column is a nullable String(64): operationId shapes in field-map.json are
short slugs (xy-tasks-01..31, red-tasks-01, device-probe) and the API layer
already caps operationId at 64 characters (PlatformTaskCreate). Existing rows
keep NULL — pre-migration tasks were not minted through the catalog factory
and must not be retro-guessed. batch_alter_table keeps the change portable
across PostgreSQL and SQLite.
"""

import sqlalchemy as sa
from alembic import op

revision = "20260916_0022"
down_revision = "20260915_0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("mobile_task") as batch:
        batch.add_column(sa.Column("operation_id", sa.String(64), nullable=True))
        batch.create_index("ix_mobile_task_operation_id", ["operation_id"])


def downgrade() -> None:
    with op.batch_alter_table("mobile_task") as batch:
        batch.drop_index("ix_mobile_task_operation_id")
        batch.drop_column("operation_id")
