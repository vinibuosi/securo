"""Preserve provider reserve snapshots and official credit metadata.

Additive and nullable: existing accounts, credentials and balances are unchanged.
"""
from alembic import op
from alembic.util import CommandError
import sqlalchemy as sa

revision = "101"
down_revision = "100"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("accounts", sa.Column("provider_metadata", sa.JSON(), nullable=True))


def downgrade() -> None:
    raise CommandError("101 preserves financial reconciliation data; restore a backup instead.")
