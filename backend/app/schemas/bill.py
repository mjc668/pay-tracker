from datetime import date, datetime, timedelta
from decimal import Decimal
from pydantic import (
    BaseModel,
    Field,
    computed_field,
    field_validator,
    model_validator,
)
from app.models.bill import BillCategory, BillFrequency, PaymentStatus


class BillTemplateCreate(BaseModel):
    name: str
    category: BillCategory
    frequency: BillFrequency
    interval_count: int = Field(1, ge=1)
    start_date: date | None = None  # weekly anchor ("first payment date")
    amount: Decimal = Decimal("0")
    currency: str = "PLN"
    due_day: int | None = Field(None, ge=1, le=31)
    due_month: int | None = Field(None, ge=1, le=12)  # month for annual/one_off
    notes: str | None = None
    is_paused: bool = False


class BillTemplateUpdate(BaseModel):
    name: str | None = None
    category: BillCategory | None = None
    frequency: BillFrequency | None = None
    interval_count: int | None = Field(None, ge=1)
    start_date: date | None = None
    amount: Decimal | None = None
    currency: str | None = None
    due_day: int | None = Field(None, ge=1, le=31)
    due_month: int | None = Field(None, ge=1, le=12)  # month for annual/one_off
    notes: str | None = None
    is_paused: bool | None = None
    recreate_deleted_future: bool = False  # transient control flag — not persisted


class BillTemplateOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    name: str
    category: BillCategory
    frequency: BillFrequency
    interval_count: int = 1
    start_date: date | None = None
    amount: Decimal
    currency: str
    due_day: int | None
    notes: str | None
    is_archived: bool
    is_paused: bool
    created_at: datetime
    start_period: str | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def due_month(self) -> int | None:
        if self.start_period:
            return int(self.start_period.split("-")[1])
        return None


class PaymentOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    instance_id: int
    amount: Decimal
    paid_on: date
    note: str | None
    created_at: datetime


class PaymentInstanceOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    bill_id: int
    period: str
    due_date: date
    amount: Decimal
    status: PaymentStatus
    paid_at: datetime | None
    paid_amount: Decimal | None
    notes: str | None
    bill_name: str
    currency: str
    frequency: BillFrequency
    interval_count: int = 1
    start_date: date | None = None
    category: BillCategory
    email_sent_at: datetime | None
    payments: list[PaymentOut] = []


class PaymentCreate(BaseModel):
    amount: Decimal = Field(gt=0)
    paid_on: date | None = None  # null means "today"
    note: str | None = None

    @field_validator("paid_on")
    @classmethod
    def reject_future_dates(cls, v: date | None) -> date | None:
        # One day of slack: a user ahead of UTC (up to +14) can legitimately
        # record a payment dated "tomorrow" in server-UTC terms.
        if v is not None and v > date.today() + timedelta(days=1):
            raise ValueError("paid_on cannot be in the future")
        return v


class MarkPaidRequest(BaseModel):
    paid_amount: Decimal | None = None  # defaults to remaining balance when None
    notes: str | None = None


class HasDeletedFutureOut(BaseModel):
    has_deleted_future: bool


class GenerateInstancesRequest(BaseModel):
    months: int = Field(6, ge=1, le=24)
    bill_ids: list[int] | None = None


class GenerateInstancesOut(BaseModel):
    created: int
    bill_count: int
    months: int


_LEGACY_FREQUENCY_INTERVALS: dict[str, int] = {
    "every_2_months": 2,
    "quarterly": 3,
}


class BackupTemplate(BaseModel):
    id: int
    name: str
    category: str | None
    frequency: BillFrequency
    interval_count: int = Field(1, ge=1)
    start_date: str | None = None
    amount: Decimal
    currency: str
    due_day: int | None
    notes: str | None
    is_archived: bool
    is_paused: bool
    start_period: str | None
    created_at: str

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_frequency(cls, data: object) -> object:
        """Map pre-v5 `every_2_months`/`quarterly` to monthly + interval.

        Only applies when the payload carries no explicit `interval_count`
        (v5 exports always do), so a v5 backup is never rewritten.
        """
        if not isinstance(data, dict):
            return data
        interval = _LEGACY_FREQUENCY_INTERVALS.get(str(data.get("frequency")))
        if interval is None or data.get("interval_count") is not None:
            return data
        return {**data, "frequency": "monthly", "interval_count": interval}


class BackupInstance(BaseModel):
    # Intentionally excluded from backup: reminder_sent_2_days_before,
    # reminder_sent_on_day, email_sent_at — transient flags reset to False on restore.
    id: int
    bill_id: int
    period: str
    due_date: str
    amount: Decimal
    status: PaymentStatus
    paid_at: str | None
    paid_amount: Decimal | None
    notes: str | None
    created_at: str
    reminder_sent_upcoming: bool = False
    reminder_sent_overdue: bool = False


class BackupPayment(BaseModel):
    id: int
    instance_id: int
    amount: Decimal
    paid_on: str
    note: str | None
    created_at: str


class BackupPayload(BaseModel):
    schema_version: int
    bill_templates: list[BackupTemplate]
    payment_instances: list[BackupInstance]
    payments: list[BackupPayment] = []


class ExportSummaryOut(BaseModel):
    bill_count: int
    payment_count: int


class RestoreSnapshotOut(BaseModel):
    created_at: datetime
