"""mobile_action_commit.platform_account_id: real platform account column (A13).

Contract: contracts/fleet/v1/fleet-identity-v1.md (fleet-identity/v1@20260916.1,
FROZEN, §2 recorded debt + §4 stable identity). The steps families feed the
deviceId into parameterHash as the account input — that input is frozen
cross-language (Kotlin ControlledActionIdentity + steps-identity-golden.json),
so the server must NOT change the hash inputs. Instead the ledger records the
real platform account (MobileTaskRow.account_id) in a new nullable column:

- intent writes ``platform_account_id = task.account_id`` (probe and steps
  uniformly); tasks without a platform account keep NULL.
- The column is intentionally NOT part of the immutable identity comparison
  (``_matches``): pre-migration rows replay with NULL and stay compatible,
  and the frozen digests are untouched.
- Downgrade simply drops the column — it holds derivable attribution data
  only; no authoritative state is lost. batch_alter_table keeps the change
  portable across PostgreSQL and SQLite (0022 precedent).
"""

import sqlalchemy as sa
from alembic import op

revision = "20260916_0024"
down_revision = "20260916_0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("mobile_action_commit") as batch:
        batch.add_column(sa.Column("platform_account_id", sa.String(36), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("mobile_action_commit") as batch:
        batch.drop_column("platform_account_id")
