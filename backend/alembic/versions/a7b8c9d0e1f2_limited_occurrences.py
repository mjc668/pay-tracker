"""limited occurrences

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-09-25 12:30:00.000000

Hand-written per context/foundation/lessons.md — do not trust autogenerate.
Adds the optional per-template occurrence cap. Nullable with no server_default:
NULL means unlimited (existing rows keep recurring forever).
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, Sequence[str], None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "bill_templates",
        sa.Column("max_occurrences", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("bill_templates", "max_occurrences")
