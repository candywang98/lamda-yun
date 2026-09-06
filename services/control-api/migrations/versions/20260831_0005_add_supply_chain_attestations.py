"""add automation and APK supply-chain attestations

Revision ID: 20260831_0005
Revises: 20260831_0004
Create Date: 2026-08-31 13:20:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260831_0005"
down_revision: str | Sequence[str] | None = "20260831_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ZERO_DIGEST = "0" * 64


def upgrade() -> None:
    op.add_column(
        "automation_package_version",
        sa.Column(
            "signature_digest", sa.String(length=64), server_default=ZERO_DIGEST, nullable=False
        ),
    )
    op.add_column(
        "automation_package_version",
        sa.Column("sbom_sha256", sa.String(length=64), server_default=ZERO_DIGEST, nullable=False),
    )
    op.add_column(
        "automation_package_version",
        sa.Column("rollout_percentage", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "automation_package_version",
        sa.Column("rollout_evidence", sa.JSON(), server_default="[]", nullable=False),
    )
    op.execute(
        sa.text(
            "UPDATE automation_package_version "
            "SET production_qualified = false, rollout_percentage = 0"
        )
    )

    op.add_column(
        "apk_artifact",
        sa.Column("sbom_sha256", sa.String(length=64), server_default=ZERO_DIGEST, nullable=False),
    )
    op.add_column(
        "apk_artifact",
        sa.Column(
            "analysis_key_id",
            sa.String(length=160),
            server_default="legacy-unverified",
            nullable=False,
        ),
    )
    op.add_column(
        "apk_artifact",
        sa.Column(
            "analysis_signature_digest",
            sa.String(length=64),
            server_default=ZERO_DIGEST,
            nullable=False,
        ),
    )
    op.add_column(
        "apk_artifact",
        sa.Column("analysis_report", sa.JSON(), server_default="{}", nullable=False),
    )
    op.add_column(
        "apk_artifact",
        sa.Column(
            "policy_decision",
            sa.JSON(),
            server_default='{"decision":"PENDING_REANALYSIS"}',
            nullable=False,
        ),
    )
    op.execute(sa.text("UPDATE apk_artifact SET scan_status = 'PENDING'"))


def downgrade() -> None:
    for column in (
        "policy_decision",
        "analysis_report",
        "analysis_signature_digest",
        "analysis_key_id",
        "sbom_sha256",
    ):
        op.drop_column("apk_artifact", column)
    for column in (
        "rollout_evidence",
        "rollout_percentage",
        "sbom_sha256",
        "signature_digest",
    ):
        op.drop_column("automation_package_version", column)
