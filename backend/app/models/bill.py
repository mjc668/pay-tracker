from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.payment import Payment
    from app.models.user import User


class BillCategory(str, Enum):
    housing = "housing"
    utilities = "utilities"
    insurance = "insurance"
    subscriptions = "subscriptions"
    entertainment = "entertainment"
    transport = "transport"
    healthcare = "healthcare"
    education = "education"
    other = "other"


class BillFrequency(str, Enum):
    monthly = "monthly"
    every_2_months = "every_2_months"
    quarterly = "quarterly"
    annual = "annual"
    one_off = "one_off"


class PaymentStatus(str, Enum):
    upcoming = "upcoming"
    overdue = "overdue"
    paid = "paid"


class BillTemplate(Base):
    """Recurring bill definition. Instances are generated from this."""

    __tablename__ = "bill_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[BillCategory] = mapped_column(String(50), nullable=False)
    frequency: Mapped[BillFrequency] = mapped_column(String(20), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="PLN")
    due_day: Mapped[int | None] = mapped_column(
        Integer
    )  # day-of-month for monthly bills
    notes: Mapped[str | None] = mapped_column(Text)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    is_paused: Mapped[bool] = mapped_column(Boolean, default=False)
    # Recurrence anchor: YYYY-MM string set at creation from UTC month.
    # Avoids UTC-vs-local off-by-one when created_at straddles a month boundary.
    # NULL for rows created before this column existed; code falls back to created_at.
    start_period: Mapped[str | None] = mapped_column(String(7))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    user: Mapped[User] = relationship(back_populates="bills")
    instances: Mapped[list["PaymentInstance"]] = relationship(
        back_populates="template", cascade="all, delete-orphan"
    )


class PaymentInstance(Base):
    """A single payment record for a specific period. Idempotent: (bill_id, period) is unique."""

    __tablename__ = "payment_instances"
    __table_args__ = (
        UniqueConstraint("bill_id", "period", name="uq_payment_instance_bill_period"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    bill_id: Mapped[int] = mapped_column(
        ForeignKey("bill_templates.id"), nullable=False
    )
    period: Mapped[str] = mapped_column(String(7), nullable=False)  # "YYYY-MM"
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    status: Mapped[PaymentStatus] = mapped_column(
        String(10), nullable=False, default=PaymentStatus.upcoming
    )
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paid_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    notes: Mapped[str | None] = mapped_column(Text)
    is_deleted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    reminder_sent_upcoming: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    reminder_sent_overdue: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    reminder_sent_2_days_before: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    reminder_sent_on_day: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    email_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    template: Mapped["BillTemplate"] = relationship(back_populates="instances")
    payments: Mapped[list["Payment"]] = relationship(
        back_populates="instance",
        cascade="all, delete-orphan",
        order_by="Payment.paid_on, Payment.id",
    )
