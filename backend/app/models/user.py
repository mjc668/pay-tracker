from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.bill import BillTemplate


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    token_version: Mapped[int] = mapped_column(
        nullable=False, default=0, server_default="0"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    language_preference: Mapped[str | None] = mapped_column(
        String(5), nullable=True, default=None
    )
    default_currency: Mapped[str | None] = mapped_column(
        String(10), nullable=True, default=None
    )
    email_reminders_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    notify_2_days_before: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    notify_1_day_before: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    notify_on_day: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    notify_1_day_after: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    reminder_send_minute: Mapped[int] = mapped_column(
        nullable=False, default=480, server_default="480"
    )
    monthly_summary_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    monthly_summary_last_sent: Mapped[str | None] = mapped_column(
        String(7), nullable=True, default=None, server_default="null"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    bills: Mapped[list[BillTemplate]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
