"""Include platform in the IM thread natural key (pa-im-m3/20260922.1 C3).

Historical message dedupe keys are deliberately untouched. Both directions first
refuse a state that the target unique constraint cannot represent; no thread or
message is merged or deleted.
"""

import sqlalchemy as sa
from alembic import op

revision = "20260923_0033"
down_revision = "20260920_0032"
branch_labels = None
depends_on = None


def _assert_one_platform_per_legacy_key() -> None:
    connection = op.get_bind()
    conflicts = connection.execute(
        sa.text(
            """
            SELECT tenant_id, device_id, peer_key,
                   COUNT(DISTINCT platform) AS platform_count
            FROM im_thread
            GROUP BY tenant_id, device_id, peer_key
            HAVING COUNT(DISTINCT platform) > 1
            ORDER BY tenant_id, device_id, peer_key
            """
        )
    ).fetchall()
    if conflicts:
        sample = ", ".join(
            f"({row.tenant_id}, {row.device_id}, {row.peer_key}, {row.platform_count})"
            for row in conflicts[:10]
        )
        raise RuntimeError(
            "IM thread platform conflict blocks constraint migration; "
            f"conflicting (tenant, device, peer, platform_count): {sample}"
        )


def upgrade() -> None:
    _assert_one_platform_per_legacy_key()
    with op.batch_alter_table("im_thread") as batch:
        batch.drop_constraint("uq_im_thread_peer", type_="unique")
        batch.create_unique_constraint(
            "uq_im_thread_platform_peer",
            ["tenant_id", "device_id", "platform", "peer_key"],
        )


def downgrade() -> None:
    _assert_one_platform_per_legacy_key()
    with op.batch_alter_table("im_thread") as batch:
        batch.drop_constraint("uq_im_thread_platform_peer", type_="unique")
        batch.create_unique_constraint(
            "uq_im_thread_peer",
            ["tenant_id", "device_id", "peer_key"],
        )
