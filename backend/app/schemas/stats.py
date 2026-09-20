from datetime import date
from decimal import Decimal

from pydantic import BaseModel

from app.models.bill import BillCategory, PaymentStatus


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


class CategoryStat(BaseModel):
    category: BillCategory
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
    by_category: list[CategoryStat]
    attention: list[AttentionItem]
