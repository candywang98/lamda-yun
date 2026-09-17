"""apk_release / apk_release_target: APK release registry + ring rollout (U10).

Contract: contracts/apk-release/v1/README.md (apk-release/v1@20260917.1,
FROZEN). Two new tables, disjoint from the P14 recipe lifecycle:

- ``apk_release``         — one immutable rollout record per *admitted*
  ``apk_artifact``: ring (canary/early/all), minimum device capability,
  data-schema compatibility window, ``requires_user_confirmation``.
  ``(tenant_id, artifact_id)`` is unique: a published artifact can never be
  overwritten (same id again → 409 APK_RELEASE_EXISTS); retiring flips status
  only.
- ``apk_release_target``  — per-device install candidate (the pin). Survives
  release retirement so already-pinned versions keep resolving. Partial
  unique index keeps one OFFERED candidate per (device, package).

The downgrade simply drops both tables: release/target rows are derivable
from the upstream admission ledger (apk_artifact) plus audit events, and no
authoritative state must survive a rollback.
"""

import sqlalchemy as sa
from alembic import op

revision = "20260917_0025"
down_revision = "20260916_0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "apk_release",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("artifact_id", sa.String(36), nullable=False),
        sa.Column("ring", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("min_capability", sa.JSON(), nullable=False),
        sa.Column("data_schema", sa.JSON(), nullable=False),
        sa.Column("requires_user_confirmation", sa.Boolean(), nullable=False),
        sa.Column("released_by", sa.String(36), nullable=False),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retired_by", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["artifact_id"], ["apk_artifact.id"]),
        sa.UniqueConstraint("tenant_id", "artifact_id", name="uq_apk_release_artifact"),
        sa.CheckConstraint("ring IN ('canary','early','all')", name="ck_apk_release_ring"),
        sa.CheckConstraint("status IN ('ACTIVE','RETIRED')", name="ck_apk_release_status"),
    )
    op.create_index("ix_apk_release_tenant_id", "apk_release", ["tenant_id"])
    op.create_index("ix_apk_release_artifact_id", "apk_release", ["artifact_id"])
    op.create_table(
        "apk_release_target",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("release_id", sa.String(36), nullable=False),
        sa.Column("device_id", sa.String(36), nullable=False),
        sa.Column("package_name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("requires_user_confirmation", sa.Boolean(), nullable=False),
        sa.Column("assigned_by", sa.String(36), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["release_id"], ["apk_release.id"]),
        sa.ForeignKeyConstraint(["device_id"], ["device.id"]),
        sa.UniqueConstraint("tenant_id", "device_id", "release_id", name="uq_apk_release_target"),
        sa.CheckConstraint(
            "status IN ('OFFERED','DOWNLOADED','INSTALLED')",
            name="ck_apk_release_target_status",
        ),
    )
    op.create_index("ix_apk_release_target_tenant_id", "apk_release_target", ["tenant_id"])
    op.create_index("ix_apk_release_target_release_id", "apk_release_target", ["release_id"])
    op.create_index("ix_apk_release_target_device_id", "apk_release_target", ["device_id"])
    op.create_index(
        "uq_apk_release_target_offered",
        "apk_release_target",
        ["device_id", "package_name"],
        unique=True,
        sqlite_where=sa.text("status = 'OFFERED'"),
        postgresql_where=sa.text("status = 'OFFERED'"),
    )


def downgrade() -> None:
    op.drop_index("uq_apk_release_target_offered", table_name="apk_release_target")
    op.drop_index("ix_apk_release_target_device_id", table_name="apk_release_target")
    op.drop_index("ix_apk_release_target_release_id", table_name="apk_release_target")
    op.drop_index("ix_apk_release_target_tenant_id", table_name="apk_release_target")
    op.drop_table("apk_release_target")
    op.drop_index("ix_apk_release_artifact_id", table_name="apk_release")
    op.drop_index("ix_apk_release_tenant_id", table_name="apk_release")
    op.drop_table("apk_release")
