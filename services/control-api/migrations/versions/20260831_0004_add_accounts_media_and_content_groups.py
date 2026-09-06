"""add accounts, media pipeline, and content groups

Revision ID: 20260831_0004
Revises: 20260831_0003
Create Date: 2026-08-31 12:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260831_0004"
down_revision: str | Sequence[str] | None = "20260831_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "content_item",
        sa.Column("status", sa.String(length=32), server_default="ACTIVE", nullable=False),
    )
    op.add_column(
        "content_item", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_table(
        "platform_account",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("platform", sa.String(length=160), nullable=False),
        sa.Column("external_subject_ref", sa.String(length=255), nullable=False),
        sa.Column("display_label", sa.String(length=160), nullable=False),
        sa.Column("secret_ref", sa.String(length=512), nullable=False),
        sa.Column("authorization_basis", sa.String(length=1000), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "platform", "external_subject_ref"),
    )
    op.create_index("ix_platform_account_tenant_id", "platform_account", ["tenant_id"])
    op.create_index("ix_platform_account_platform", "platform_account", ["platform"])
    op.create_index("ix_platform_account_status", "platform_account", ["status"])
    op.create_table(
        "account_device_binding",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("account_id", sa.String(length=36), nullable=False),
        sa.Column("device_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("confirmed_by", sa.String(length=36), nullable=False),
        sa.Column("confirmation_note", sa.String(length=1000), nullable=False),
        sa.Column("bound_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("unbound_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["platform_account.id"]),
        sa.ForeignKeyConstraint(["device_id"], ["device.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id", "device_id"),
    )
    for column in ("tenant_id", "account_id", "device_id", "status"):
        op.create_index(f"ix_account_device_binding_{column}", "account_device_binding", [column])
    op.create_table(
        "media_upload",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("expected_sha256", sa.String(length=64), nullable=False),
        sa.Column("object_key", sa.String(length=512), nullable=False),
        sa.Column("content_type", sa.String(length=160), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("source_asset_id", sa.String(length=36), nullable=True),
        sa.Column("derivative_profile_id", sa.String(length=160), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("object_key"),
    )
    op.create_index("ix_media_upload_tenant_id", "media_upload", ["tenant_id"])
    op.create_index("ix_media_upload_state", "media_upload", ["state"])
    op.create_table(
        "media_derivative",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("source_asset_id", sa.String(length=36), nullable=False),
        sa.Column("profile_id", sa.String(length=160), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("output_asset_id", sa.String(length=36), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("tenant_id", "source_asset_id", "state"):
        op.create_index(f"ix_media_derivative_{column}", "media_derivative", [column])
    op.create_table(
        "content_group",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "name"),
    )
    op.create_index("ix_content_group_tenant_id", "content_group", ["tenant_id"])
    op.create_table(
        "content_group_membership",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("group_id", sa.String(length=36), nullable=False),
        sa.Column("content_id", sa.String(length=36), nullable=False),
        sa.Column("added_by", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["content_id"], ["content_item.id"]),
        sa.ForeignKeyConstraint(["group_id"], ["content_group.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("group_id", "content_id"),
    )
    for column in ("tenant_id", "group_id", "content_id"):
        op.create_index(
            f"ix_content_group_membership_{column}", "content_group_membership", [column]
        )


def downgrade() -> None:
    op.drop_table("content_group_membership")
    op.drop_table("content_group")
    op.drop_table("media_derivative")
    op.drop_table("media_upload")
    op.drop_table("account_device_binding")
    op.drop_table("platform_account")
    op.drop_column("content_item", "archived_at")
    op.drop_column("content_item", "status")
