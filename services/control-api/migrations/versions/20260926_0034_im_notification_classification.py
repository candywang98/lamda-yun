"""Add notification classification sidecars without rewriting message history."""

import sqlalchemy as sa
from alembic import op

revision = "20260926_0034"
down_revision = "20260923_0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "im_message_classification",
        sa.Column("message_id", sa.String(36), sa.ForeignKey("im_message.id"), primary_key=True),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("notification_metadata", sa.JSON()),
        sa.Column("notification_title", sa.String(128)),
        sa.Column("machine_category", sa.String(32), nullable=False),
        sa.Column("machine_source", sa.String(24), nullable=False),
        sa.Column("machine_status", sa.String(32), nullable=False),
        sa.Column("predicted_category", sa.String(32)),
        sa.Column("confidence", sa.Float()),
        sa.Column("model_status", sa.String(32)),
        sa.Column("rule_code", sa.String(64)),
        sa.Column("manual_category", sa.String(32)),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("reviewed_by", sa.String(36)),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version >= 1 AND generation >= 1", name="ck_im_classification_version"),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_im_classification_confidence",
        ),
    )
    op.create_index(
        "ix_im_message_classification_tenant_id", "im_message_classification", ["tenant_id"]
    )


def downgrade() -> None:
    op.drop_table("im_message_classification")
