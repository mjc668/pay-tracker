from datetime import date
from decimal import Decimal

from pydantic import BaseModel

from app.models.bill import PaymentStatus
from app.schemas.category import CategoryOut


class StatsSummary(BaseModel):
    due_total: Decimal
    paid_total: Decimal
    remaining_total: Decimal
    total_count: int
    paid_count: int
    upcoming_count: int
    overdue_count: int
    overdue_total: Decimal


class TrendPoint(BaseModel):
    period: str
    paid_total: Decimal
    due_total: Decimal


class ForecastPoint(BaseModel):
    """Expected spend for a future period.

    Always exactly 6 points (`month+1` … `month+6`, oldest first), independent
    of the requested `months` window. Existing instances are not subtracted —
    this is an expectation, not a remaining balance.
    """

    period: str
    expected_total: Decimal


class UpcomingWindow(BaseModel):
    """Rolling window from today: unpaid instances due within N days."""

    count: int
    total: Decimal


class PaidWindow(BaseModel):
    """Rolling window ending today: paid vs due over the last 30 days."""

    paid_total: Decimal
    due_total: Decimal


class CategoryStat(BaseModel):
    category: CategoryOut
    paid_total: Decimal
    due_total: Decimal


class AttentionItem(BaseModel):
    instance_id: int
    period: str
    bill_name: str
    due_date: date
    amount: Decimal
    paid_amount: Decimal | None
    remaining: Decimal
    status: PaymentStatus


class StatsOverviewOut(BaseModel):
    month: str
    months: int
    currency: str
    other_currencies: list[str]
    summary: StatsSummary
    trend: list[TrendPoint]
    forecast: list[ForecastPoint]
    upcoming_7d: UpcomingWindow
    upcoming_30d: UpcomingWindow
    paid_30d: PaidWindow
    by_category: list[CategoryStat]
    attention: list[AttentionItem]
