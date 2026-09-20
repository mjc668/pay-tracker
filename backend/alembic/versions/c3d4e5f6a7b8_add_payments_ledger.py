"""add payments ledger

Revision ID: c3d4e5f6a7b8
Revises: e1f2a3b4c5d6
Create Date: 2026-09-20 14:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, Sequence[str], None] = "e1f2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "payments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("instance_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("paid_on", sa.Date(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["instance_id"],
            ["payment_instances.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_payments_instance_id", "payments", ["instance_id"])

    # Backfill one event per already-paid instance.
    op.execute("""
        INSERT INTO payments (instance_id, amount, paid_on, note, created_at)
        SELECT id, COALESCE(paid_amount, amount), COALESCE(paid_at::date, due_date), notes,
               COALESCE(paid_at, created_at)
        FROM payment_instances
        WHERE status = 'paid'
        """)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_payments_instance_id", table_name="payments")
    op.drop_table("payments")
