"""xianyu_delete_evidence: X10 delete approval ledger + readback results.

Two tables for the P09 delete evidence loop (fleet-first-20260916.1 X10):

- ``xianyu_delete_approval`` — the per-target operator approval (account /
  identity evidence / frozen action / validity window). The single confirm
  issuance moves APPROVED -> CONSUMED and records the one issued taskId; the
  cancel loop records ABORTED_BY_OPERATOR; operator resolution (gated on the
  A13 ledger closure proof) records RESOLVED.
- ``xianyu_delete_result`` — the readback verdict per approval (one row per
  approval, replay-checked), reconciled against the frozen
  ``mobile_action_commit`` confirm-delete row.

ORM counterparts live in ``cloudctl_api/xianyu_delete_evidence.py`` (db.py is
not touched by X10, same pattern as P10's xianyu_publish_target). Protection
period is NEVER stored: it is derived from an unresolved CONSUMED approval —
an explicit rejection cause, not a countdown.

Downgrade drops both tables: approvals/results are queue-derivable state, the
audit trail and the A13 ledger keep the authoritative history.
"""

import sqlalchemy as sa
from alembic import op

revision = "20260917_0029"
down_revision = "20260917_0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "xianyu_delete_approval",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("device_id", sa.String(36), nullable=False),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("target_key", sa.String(256), nullable=False),
        sa.Column("identity_evidence", sa.JSON(), nullable=False),
        sa.Column("action", sa.String(48), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("issued_task_id", sa.String(36), nullable=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("requested_by", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "state IN ('APPROVED','CONSUMED','ABORTED_BY_OPERATOR','RESOLVED')",
            name="ck_xianyu_delete_approval_state",
        ),
        sa.CheckConstraint("valid_until > valid_from", name="ck_xianyu_delete_approval_window"),
        sa.CheckConstraint("action = 'delete-delisted'", name="ck_xianyu_delete_approval_action"),
    )
    op.create_index("ix_xianyu_delete_approval_tenant_id", "xianyu_delete_approval", ["tenant_id"])
    op.create_index(
        "ix_xianyu_delete_approval_target_key", "xianyu_delete_approval", ["target_key"]
    )
    op.create_table(
        "xianyu_delete_result",
        sa.Column(
            "approval_id",
            sa.String(36),
            sa.ForeignKey("xianyu_delete_approval.id"),
            primary_key=True,
        ),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("task_id", sa.String(36), nullable=False),
        sa.Column("action_key", sa.String(64), nullable=False),
        sa.Column("verdict", sa.String(32), nullable=False),
        sa.Column("readback", sa.JSON(), nullable=False),
        sa.Column("resolved", sa.Boolean(), nullable=False),
        sa.Column("resolution", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "verdict IN ('VERIFIED_DELETED','PENDING_VERIFICATION','STILL_PRESENT','INCONCLUSIVE')",
            name="ck_xianyu_delete_result_verdict",
        ),
    )
    op.create_index("ix_xianyu_delete_result_tenant_id", "xianyu_delete_result", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_xianyu_delete_result_tenant_id", table_name="xianyu_delete_result")
    op.drop_table("xianyu_delete_result")
    op.drop_index("ix_xianyu_delete_approval_target_key", table_name="xianyu_delete_approval")
    op.drop_index("ix_xianyu_delete_approval_tenant_id", table_name="xianyu_delete_approval")
    op.drop_table("xianyu_delete_approval")
