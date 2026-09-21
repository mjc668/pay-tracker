"""editable categories

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-09-21 14:00:00.000000

Hand-written per context/foundation/lessons.md — do not trust autogenerate.
Replaces the fixed `bill_templates.category` enum string with a per-user
`categories` table. Existing users get the nine default rows seeded; every
bill is backfilled to its matching default key, falling back to `other`.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, Sequence[str], None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_DEFAULT_KEYS = (
    "housing",
    "utilities",
    "insurance",
    "subscriptions",
    "entertainment",
    "transport",
    "healthcare",
    "education",
    "other",
)

_FK_NAME = "fk_bill_templates_category_id_categories"


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=50), nullable=True),
        sa.Column("name", sa.String(length=100), nullable=True),
        sa.Column(
            "is_archived", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_categories_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "key", name="uq_categories_user_id_key"),
        sa.UniqueConstraint("user_id", "name", name="uq_categories_user_id_name"),
    )
    op.create_index("ix_categories_user_id", "categories", ["user_id"])

    # Seed the nine defaults for every existing user.
    keys_values = ", ".join(f"('{key}')" for key in _DEFAULT_KEYS)
    op.execute(
        "INSERT INTO categories (user_id, key, name, is_archived, created_at) "
        "SELECT u.id, k.key, NULL, false, now() "
        "FROM users u CROSS JOIN (VALUES " + keys_values + ") AS k(key)"
    )

    # Add the FK column nullable first so the backfill can run.
    op.add_column(
        "bill_templates",
        sa.Column("category_id", sa.Integer(), nullable=True),
    )
    op.execute(
        "UPDATE bill_templates bt SET category_id = c.id "
        "FROM categories c "
        "WHERE c.user_id = bt.user_id AND c.key = bt.category"
    )
    # Unmatched/legacy values fall back to that user's `other` category.
    op.execute(
        "UPDATE bill_templates bt SET category_id = c.id "
        "FROM categories c "
        "WHERE c.user_id = bt.user_id AND c.key = 'other' "
        "AND bt.category_id IS NULL"
    )
    op.alter_column(
        "bill_templates", "category_id", existing_type=sa.Integer(), nullable=False
    )
    op.create_foreign_key(
        _FK_NAME,
        "bill_templates",
        "categories",
        ["category_id"],
        ["id"],
    )
    op.drop_column("bill_templates", "category")


def downgrade() -> None:
    """Downgrade schema (best-effort: custom categories collapse to `other`)."""
    op.add_column(
        "bill_templates",
        sa.Column("category", sa.String(length=50), nullable=True),
    )
    op.execute(
        "UPDATE bill_templates bt SET category = COALESCE(c.key, 'other') "
        "FROM categories c WHERE c.id = bt.category_id"
    )
    op.alter_column(
        "bill_templates",
        "category",
        existing_type=sa.String(length=50),
        nullable=False,
    )
    op.drop_constraint(_FK_NAME, "bill_templates", type_="foreignkey")
    op.drop_column("bill_templates", "category_id")
    op.drop_index("ix_categories_user_id", table_name="categories")
    op.drop_table("categories")
