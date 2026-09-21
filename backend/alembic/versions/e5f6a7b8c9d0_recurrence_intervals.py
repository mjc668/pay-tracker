"""recurrence intervals (weekly unit + every-N months/years)

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-09-21 12:00:00.000000

Hand-written per context/foundation/lessons.md — do not trust autogenerate.
Swaps the PaymentInstance idempotency key from (bill_id, period) to
(bill_id, due_date) so weekly bills can produce several occurrences per month.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, Sequence[str], None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # NOT NULL with a server default, then drop the default so the ORM's
    # Python-side default=1 is the only source for new rows.
    op.add_column(
        "bill_templates",
        sa.Column("interval_count", sa.Integer(), nullable=False, server_default="1"),
    )
    op.alter_column(
        "bill_templates",
        "interval_count",
        existing_type=sa.Integer(),
        server_default=None,
    )
    op.add_column(
        "bill_templates",
        sa.Column("start_date", sa.Date(), nullable=True),
    )

    # Legacy frequency values become monthly + interval.
    op.execute(
        "UPDATE bill_templates SET interval_count = 2 "
        "WHERE frequency = 'every_2_months'"
    )
    op.execute(
        "UPDATE bill_templates SET interval_count = 3 " "WHERE frequency = 'quarterly'"
    )
    op.execute(
        "UPDATE bill_templates SET frequency = 'monthly' "
        "WHERE frequency IN ('every_2_months', 'quarterly')"
    )

    op.drop_constraint(
        "uq_payment_instance_bill_period", "payment_instances", type_="unique"
    )
    op.create_unique_constraint(
        "uq_payment_instance_bill_due_date",
        "payment_instances",
        ["bill_id", "due_date"],
    )


def downgrade() -> None:
    """Downgrade schema (best-effort: weekly schedules are not representable
    in the old enum and are flattened to monthly/1; restoring the old
    (bill_id, period) unique constraint fails if a weekly bill still has
    several occurrences in one period)."""
    op.execute(
        "UPDATE bill_templates SET frequency = 'monthly', interval_count = 1 "
        "WHERE frequency = 'weekly'"
    )
    op.execute(
        "UPDATE bill_templates SET frequency = 'every_2_months', interval_count = 1 "
        "WHERE frequency = 'monthly' AND interval_count = 2"
    )
    op.execute(
        "UPDATE bill_templates SET frequency = 'quarterly', interval_count = 1 "
        "WHERE frequency = 'monthly' AND interval_count = 3"
    )
    op.execute("UPDATE bill_templates SET interval_count = 1 WHERE interval_count > 1")

    op.drop_constraint(
        "uq_payment_instance_bill_due_date", "payment_instances", type_="unique"
    )
    op.create_unique_constraint(
        "uq_payment_instance_bill_period",
        "payment_instances",
        ["bill_id", "period"],
    )
    op.drop_column("bill_templates", "start_date")
    op.drop_column("bill_templates", "interval_count")
