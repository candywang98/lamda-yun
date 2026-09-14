"""WeChat Official Account publisher tables (V1-26 API publisher starter slice).

Adds the server-side credential registry (encrypted appSecret envelope), the
draft box mirror, and the publish ledger whose CHECK constraints enforce the
controlled-commit semantics: one authorization row per draft and at most one
submit attempt per publish.
"""

import sqlalchemy as sa
from alembic import op

revision = "20260915_0019"
down_revision = "20260914_0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "wechat_account",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), nullable=False, index=True),
        sa.Column("app_id", sa.String(64), nullable=False),
        sa.Column("display_label", sa.String(160), nullable=False),
        sa.Column("secret_ciphertext", sa.String(2048), nullable=False),
        sa.Column("secret_fingerprint", sa.String(64), nullable=False),
        sa.Column("secret_key_id", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, index=True, server_default="ACTIVE"),
        sa.Column("created_by", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("tenant_id", "app_id", name="uq_wechat_account_tenant_app"),
        sa.CheckConstraint("status IN ('ACTIVE', 'REVOKED')", name="ck_wechat_account_status"),
    )
    op.create_table(
        "wechat_draft",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), nullable=False, index=True),
        sa.Column(
            "account_id",
            sa.String(36),
            sa.ForeignKey("wechat_account.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_sha256", sa.String(64), nullable=False),
        sa.Column("article", sa.JSON(), nullable=False),
        sa.Column("article_sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, index=True, server_default="PENDING"),
        sa.Column("media_id", sa.String(256), nullable=True),
        sa.Column("created_by", sa.String(36), nullable=False),
        sa.Column("error_code", sa.String(80), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_wechat_draft_idempotency"),
        sa.CheckConstraint(
            "status IN ('PENDING', 'READY', 'UNKNOWN', 'FAILED')",
            name="ck_wechat_draft_status",
        ),
    )
    op.create_table(
        "wechat_publish",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), nullable=False, index=True),
        sa.Column(
            "draft_id",
            sa.String(36),
            sa.ForeignKey("wechat_draft.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "account_id",
            sa.String(36),
            sa.ForeignKey("wechat_account.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_sha256", sa.String(64), nullable=False),
        sa.Column("parameter_hash", sa.String(64), nullable=False),
        sa.Column("authorized_by", sa.String(36), nullable=False),
        sa.Column("submitted_by", sa.String(36), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, index=True, server_default="INTENT"),
        sa.Column("publish_id", sa.String(256), nullable=True),
        sa.Column("article_url", sa.String(1024), nullable=True),
        sa.Column("submit_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("poll_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_code", sa.String(80), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_wechat_publish_idempotency"),
        sa.UniqueConstraint("draft_id", name="uq_wechat_publish_draft"),
        sa.CheckConstraint(
            "status IN ('INTENT', 'SUBMITTING', 'SUBMITTED', 'UNKNOWN', 'PUBLISHED', 'FAILED')",
            name="ck_wechat_publish_status",
        ),
        sa.CheckConstraint("submit_attempts BETWEEN 0 AND 1", name="ck_wechat_publish_one_attempt"),
    )


def downgrade() -> None:
    op.drop_table("wechat_publish")
    op.drop_table("wechat_draft")
    op.drop_table("wechat_account")
