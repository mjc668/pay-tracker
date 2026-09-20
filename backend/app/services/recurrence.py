from datetime import date, datetime, timezone
from calendar import monthrange

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.bill import BillFrequency, BillTemplate, PaymentInstance, PaymentStatus


def _add_months(period: str, delta: int) -> str:
    """Shift a "YYYY-MM" period by `delta` months."""
    year, month = map(int, period.split("-"))
    total = year * 12 + (month - 1) + delta
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


def _next_period(period: str, frequency: BillFrequency) -> str:
    year, month = map(int, period.split("-"))
    if frequency == BillFrequency.monthly:
        month += 1
        if month > 12:
            month = 1
            year += 1
    elif frequency == BillFrequency.every_2_months:
        month += 2
        while month > 12:
            month -= 12
            year += 1
    elif frequency == BillFrequency.quarterly:
        month += 3
        while month > 12:
            month -= 12
            year += 1
    elif frequency == BillFrequency.annual:
        year += 1
    return f"{year:04d}-{month:02d}"


def _due_date_for_period(period: str, due_day: int | None) -> date:
    year, month = map(int, period.split("-"))
    day = due_day or 1
    # clamp to last day of month (e.g. due_day=31 in Feb → 28/29)
    last_day = monthrange(year, month)[1]
    return date(year, month, min(day, last_day))


def _bill_active_in_period(template: BillTemplate, period: str) -> bool:
    """Return True if this template's frequency schedule falls on the given period."""
    if template.frequency == BillFrequency.monthly:
        return True

    # Use start_period (YYYY-MM) as the recurrence anchor when set.
    # Falls back to created_at UTC month for rows predating the column.
    anchor = template.start_period or template.created_at.strftime("%Y-%m")
    start_year, start_month = map(int, anchor.split("-"))
    target_year, target_month = map(int, period.split("-"))
    months_diff = (target_year - start_year) * 12 + (target_month - start_month)

    if months_diff < 0:
        return False

    if template.frequency == BillFrequency.every_2_months:
        return months_diff % 2 == 0
    if template.frequency == BillFrequency.quarterly:
        return months_diff % 3 == 0
    if template.frequency == BillFrequency.annual:
        return months_diff % 12 == 0

    return False


def backfill_template_instances(
    db: Session, template: BillTemplate, from_period: str, to_period: str
) -> int:
    """Create missing instances for a single template from from_period to to_period inclusive.

    Returns the number of instances actually inserted (0 when every active
    period already has a row, including soft-deleted tombstones).
    """
    # Collect all periods in range where this template is active.
    active_periods: list[str] = []
    year, month = map(int, from_period.split("-"))
    period = from_period
    while period <= to_period:
        if _bill_active_in_period(template, period):
            active_periods.append(period)
        month += 1
        if month > 12:
            month = 1
            year += 1
        period = f"{year:04d}-{month:02d}"

    if not active_periods:
        return 0

    # Single query for all existing periods — avoids N+1 per period.
    existing_periods = {
        row.period
        for row in db.query(PaymentInstance.period).filter(
            PaymentInstance.bill_id == template.id,
            PaymentInstance.period.in_(active_periods),
        )
    }

    created = 0
    for p in active_periods:
        if p not in existing_periods:
            db.add(
                PaymentInstance(
                    bill_id=template.id,
                    period=p,
                    due_date=_due_date_for_period(p, template.due_day),
                    amount=template.amount,
                    status=PaymentStatus.upcoming,
                )
            )
            created += 1

    if db.new:
        try:
            db.commit()
        except IntegrityError:
            # Concurrent insert won the race: the whole batch rolled back.
            db.rollback()
            return 0

    return created


def eligible_for_generation(
    db: Session, user_id: int, bill_ids: list[int] | None = None
) -> list[BillTemplate]:
    """User's non-archived, non-paused, recurring templates (optionally subset)."""
    query = db.query(BillTemplate).filter(
        BillTemplate.user_id == user_id,
        BillTemplate.is_archived.is_(False),
        BillTemplate.is_paused.is_(False),
        BillTemplate.frequency != BillFrequency.one_off,
    )
    if bill_ids is not None:
        query = query.filter(BillTemplate.id.in_(bill_ids))
    return query.order_by(BillTemplate.id).all()


def generate_future_instances(
    db: Session,
    user_id: int,
    months: int,
    bill_ids: list[int] | None = None,
) -> tuple[int, int]:
    """Generate instances for current UTC month+1 through +months inclusive.

    Returns `(created, template_count)`; creation is idempotent via the
    `(bill_id, period)` uniqueness check in `backfill_template_instances`.
    """
    current = datetime.now(timezone.utc).strftime("%Y-%m")
    from_period = _add_months(current, 1)
    to_period = _add_months(current, months)

    templates = eligible_for_generation(db, user_id, bill_ids)
    created = 0
    for template in templates:
        created += backfill_template_instances(db, template, from_period, to_period)
    return created, len(templates)


def ensure_current_period_instances(db: Session, period: str, user_id: int) -> None:
    """Idempotently seed payment instances for eligible templates that are due in period."""
    templates = (
        db.query(BillTemplate)
        .filter(
            BillTemplate.user_id == user_id,
            BillTemplate.is_archived.is_(False),
            BillTemplate.is_paused.is_(False),
            BillTemplate.frequency != BillFrequency.one_off,
        )
        .all()
    )
    for template in templates:
        if not _bill_active_in_period(template, period):
            continue
        existing = (
            db.query(PaymentInstance)
            .filter(
                PaymentInstance.bill_id == template.id,
                PaymentInstance.period == period,
            )
            .first()
        )
        if existing:
            continue
        instance = PaymentInstance(
            bill_id=template.id,
            period=period,
            due_date=_due_date_for_period(period, template.due_day),
            amount=template.amount,
            status=PaymentStatus.upcoming,
        )
        db.add(instance)
    if db.new:
        db.commit()


def generate_next_instance(
    db: Session, template: BillTemplate, paid_period: str
) -> PaymentInstance | None:
    """Create the next-period instance after a payment. Idempotent."""
    if template.frequency == BillFrequency.one_off:
        return None

    next_period = _next_period(paid_period, template.frequency)

    # idempotent: skip if already exists
    existing = (
        db.query(PaymentInstance)
        .filter(
            PaymentInstance.bill_id == template.id,
            PaymentInstance.period == next_period,
        )
        .first()
    )
    if existing:
        return existing

    instance = PaymentInstance(
        bill_id=template.id,
        period=next_period,
        due_date=_due_date_for_period(next_period, template.due_day),
        amount=template.amount,
        status=PaymentStatus.upcoming,
    )
    db.add(instance)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return (
            db.query(PaymentInstance)
            .filter(
                PaymentInstance.bill_id == template.id,
                PaymentInstance.period == next_period,
            )
            .first()
        )
    db.refresh(instance)
    return instance
