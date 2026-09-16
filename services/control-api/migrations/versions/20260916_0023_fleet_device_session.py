"""fleet_device_session: Companion session registry (fleet-identity/v1 A10).

Contract: contracts/fleet/v1/fleet-identity-v1.md (fleet-identity/v1@20260916.1,
FROZEN, §2). One row per Companion *process registration*:

- ``session_id``  — minted on every enroll/re-registration; enters the dynamic
  authorization envelope only (never actionKey/parameterHash, §4).
- ``boot_id``     — OS boot session; a lease stamped with an older boot is
  stale and cannot be revived by a late heartbeat.
- ``capabilities``— the closed V1 capability table (§3) plus the raw
  executable gate states (accessibility enabled/active, ime, screen,
  engine version).

Compatibility-first ("迁移扩展字段先可空/兼容再收紧"): every extension column
except the identity columns is nullable, there are no CHECK constraints, and
legacy devices that never negotiated a capability profile keep the pre-A10
claim behavior. The downgrade simply drops the registry — it holds no
authoritative state that survives a rollback.
"""

import sqlalchemy as sa
from alembic import op

revision = "20260916_0023"
down_revision = "20260916_0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fleet_device_session",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("session_id", sa.String(64), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("device_id", sa.String(36), nullable=False),
        sa.Column("binding_id", sa.String(36), nullable=False),
        sa.Column("boot_id", sa.String(128), nullable=True),
        sa.Column("companion_version", sa.String(128), nullable=True),
        sa.Column("engine_version", sa.Integer(), nullable=True),
        sa.Column("capabilities", sa.JSON(), nullable=True),
        sa.Column("accessibility_enabled", sa.Boolean(), nullable=True),
        sa.Column("accessibility_active", sa.Boolean(), nullable=True),
        sa.Column("ime_ready", sa.Boolean(), nullable=True),
        sa.Column("screen_unlocked", sa.Boolean(), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["device_id"], ["device.id"]),
        sa.ForeignKeyConstraint(["binding_id"], ["mobile_binding.id"]),
    )
    op.create_index(
        "ix_fleet_device_session_session_id",
        "fleet_device_session",
        ["session_id"],
        unique=True,
    )
    op.create_index("ix_fleet_device_session_tenant_id", "fleet_device_session", ["tenant_id"])
    op.create_index("ix_fleet_device_session_device_id", "fleet_device_session", ["device_id"])
    op.create_index("ix_fleet_device_session_binding_id", "fleet_device_session", ["binding_id"])


def downgrade() -> None:
    op.drop_index("ix_fleet_device_session_binding_id", table_name="fleet_device_session")
    op.drop_index("ix_fleet_device_session_device_id", table_name="fleet_device_session")
    op.drop_index("ix_fleet_device_session_tenant_id", table_name="fleet_device_session")
    op.drop_index("ix_fleet_device_session_session_id", table_name="fleet_device_session")
    op.drop_table("fleet_device_session")
