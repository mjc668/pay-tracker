from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.bill import BillTemplate
    from app.models.user import User


class Category(Base):
    """Per-user bill category.

    Default categories carry a `key` (translated in the UI via
    `Categories.<key>`) and start with `name` NULL; renaming a default stores
    a `name` override. Custom categories carry `name` only. `key`/`name`
    uniqueness is enforced per user (NULLs are distinct in PostgreSQL, so the
    two constraints do not collide for custom/default rows).
    """

    __tablename__ = "categories"
    __table_args__ = (
        UniqueConstraint("user_id", "key", name="uq_categories_user_id_key"),
        UniqueConstraint("user_id", "name", name="uq_categories_user_id_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    key: Mapped[str | None] = mapped_column(String(50))
    name: Mapped[str | None] = mapped_column(String(100))
    is_archived: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    user: Mapped[User] = relationship(back_populates="categories")
    bills: Mapped[list[BillTemplate]] = relationship(back_populates="category")
