"""xianyu_publish_target: P10 publish-target persistence (fleet-first-20260916.1).

One row per listing to place — the publish target is persisted separately
from the MobileTask identity: retries mint new tasks against the same target
(``task_ids`` is a list), the platform's external item id lands on the row
only when the result is confirmed, and the serial single-item queue advance
rule reads exactly this table (PENDING / FAILED_UNCONFIRMED are issuable;
SUCCEEDED_CONFIRMED is never redone).

ORM counterpart: ``XianyuPublishTargetRow`` in
``cloudctl_api/xianyu_publish.py`` (db.py is not touched by P10).

Downgrade drops the table: targets are queue-derivable state, not
authoritative content — the audit trail keeps the decisions.
"""

import sqlalchemy as sa
from alembic import op

revision = "20260917_0027"
down_revision = "20260917_0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "xianyu_publish_target",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("queue_id", sa.String(64), nullable=False),
        sa.Column("device_id", sa.String(36), nullable=False),
        sa.Column("account_id", sa.String(36), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("item", sa.JSON(), nullable=False),
        sa.Column("claimed_boundary", sa.String(48), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("task_ids", sa.JSON(), nullable=False),
        sa.Column("external_item_id", sa.String(64), nullable=True),
        sa.Column("recorded_boundary", sa.String(48), nullable=True),
        sa.Column("boundary_downgraded", sa.Boolean(), nullable=False),
        sa.Column("judgment", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("requested_by", sa.String(36), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        # No FK on device_id: mirrors the ORM metadata exactly (db.py stays
        # untouched by P10); device existence is enforced at request layer.
        sa.UniqueConstraint(
            "tenant_id", "queue_id", "position", name="uq_xianyu_publish_target_position"
        ),
        sa.CheckConstraint(
            "state IN ('PENDING','IN_FLIGHT','FAILED_UNCONFIRMED',"
            "'SUCCEEDED_CONFIRMED','FAILED_CONFIRMED','CANCELLED')",
            name="ck_xianyu_publish_target_state",
        ),
    )
    op.create_index(
        "ix_xianyu_publish_target_tenant_id", "xianyu_publish_target", ["tenant_id"]
    )
    op.create_index("ix_xianyu_publish_target_queue_id", "xianyu_publish_target", ["queue_id"])


def downgrade() -> None:
    op.drop_index("ix_xianyu_publish_target_queue_id", table_name="xianyu_publish_target")
    op.drop_index("ix_xianyu_publish_target_tenant_id", table_name="xianyu_publish_target")
    op.drop_table("xianyu_publish_target")
