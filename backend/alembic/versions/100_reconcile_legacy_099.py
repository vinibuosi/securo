"""Reconcile the two historical meanings of revision 099 without deleting data.

099 may mean loan columns, removal of the registration setting, or both.
Keep the loan migration as 099; databases already at either legacy 099 skip
it, so this revision must also supply missing loan columns. Preserve every
registration setting (including its absence): its provenance is unknowable.
"""

import sqlalchemy as sa
from alembic import context, op
from alembic.util import CommandError

revision = "100"
down_revision = "099"
branch_labels = None
depends_on = None


def _columns() -> list[sa.Column]:
    return [
        sa.Column("loan_kind", sa.String(20), nullable=True),
        sa.Column("loan_original_amount", sa.Numeric(15, 2), nullable=True),
        sa.Column("loan_interest_rate", sa.Numeric(9, 6), nullable=True),
        sa.Column("loan_rate_period", sa.String(20), nullable=True),
        sa.Column("loan_term_months", sa.SmallInteger(), nullable=True),
        sa.Column("loan_first_payment_date", sa.Date(), nullable=True),
        sa.Column("loan_amortization", sa.String(10), nullable=True),
    ]


def upgrade() -> None:
    if context.is_offline_mode():
        raise CommandError("Revision 100 requires an online PostgreSQL schema inspection.")
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        raise CommandError("Revision 100 requires PostgreSQL.")
    existing = {column["name"]: column for column in sa.inspect(bind).get_columns("accounts")}
    expected = _columns()
    # Validate everything before adding anything. Unknown manual changes must
    # not be silently accepted or coerced, especially financial precision.
    for column in expected:
        actual = existing.get(column.name)
        if actual is None:
            continue
        if (
            str(actual["type"].compile(dialect=bind.dialect))
            != str(column.type.compile(dialect=bind.dialect))
            or actual["nullable"] is not True
            or actual.get("default") is not None
            or actual.get("computed") is not None
            or actual.get("identity") is not None
        ):
            raise CommandError(
                f"Revision 100: incompatible accounts.{column.name}; "
                "inspect the existing definition before retrying. No columns were added."
            )
    for column in expected:
        if column.name not in existing:
            op.add_column("accounts", column)


def downgrade() -> None:
    raise CommandError(
        "Revision 100 cannot be downgraded automatically: legacy 099 does not "
        "identify which loan columns or registration settings previously existed."
    )
