from calendar import monthrange
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.bill import BillFrequency, BillTemplate, PaymentInstance, PaymentStatus

# Allowed interval_count per unit: weekly 1-4, monthly 1-12, annual 1-5.
_INTERVAL_MAX: dict[BillFrequency, int] = {
    BillFrequency.weekly: 4,
    BillFrequency.monthly: 12,
    BillFrequency.annual: 5,
    BillFrequency.one_off: 1,
}


def validate_schedule(
    frequency: BillFrequency,
    interval_count: int,
    start_date: date | None,
) -> str | None:
    """Return an error message when the effective schedule is invalid, else None.

    Callers must normalize `interval_count` to 1 for one_off bills before
    validating. `start_date` is only meaningful for weekly bills.
    """
    frequency = BillFrequency(frequency)
    if frequency == BillFrequency.one_off:
        return None
    maximum = _INTERVAL_MAX[frequency]
    if not 1 <= interval_count <= maximum:
        return f"interval_count for {frequency.value} bills must be between 1 and {maximum}"
    if frequency == BillFrequency.weekly and start_date is None:
        return "weekly bills require start_date"
    return None


def _add_months(period: str, delta: int) -> str:
    """Shift a "YYYY-MM" period by `delta` months."""
    year, month = map(int, period.split("-"))
    total = year * 12 + (month - 1) + delta
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


def _next_period(period: str, frequency: BillFrequency, interval: int) -> str:
    """Shift a month-anchored period by one recurrence step.

    Non month-anchored units (weekly/one_off) are handled by their callers;
    this returns the period unchanged for them.
    """
    if frequency == BillFrequency.monthly:
        return _add_months(period, interval)
    if frequency == BillFrequency.annual:
        return _add_months(period, 12 * interval)
    return period


def _due_date_for_period(period: str, due_day: int | None) -> date:
    year, month = map(int, period.split("-"))
    day = due_day or 1
    # clamp to last day of month (e.g. due_day=31 in Feb → 28/29)
    last_day = monthrange(year, month)[1]
    return date(year, month, min(day, last_day))


def _step_weeks(start: date, interval: int, k: int) -> date:
    """The k-th weekly occurrence after `start`: start + 7*interval*k days."""
    return start + timedelta(days=7 * interval * k)


def _step_months(template: BillTemplate) -> int:
    """Months between occurrences for month-anchored units."""
    if template.frequency == BillFrequency.annual:
        return 12 * template.interval_count
    return template.interval_count


def _bill_active_in_period(template: BillTemplate, period: str) -> bool:
    """Return True if a month-anchored template's schedule hits the period.

    Weekly templates are occurrence-based and always return False here; use
    `_occurrences_in_period` for them.
    """
    if template.frequency not in (BillFrequency.monthly, BillFrequency.annual):
        return False

    # Use start_period (YYYY-MM) as the recurrence anchor when set.
    # Falls back to created_at UTC month for rows predating the column.
    anchor = template.start_period or template.created_at.strftime("%Y-%m")
    start_year, start_month = map(int, anchor.split("-"))
    target_year, target_month = map(int, period.split("-"))
    months_diff = (target_year - start_year) * 12 + (target_month - start_month)

    if months_diff < 0:
        return False

    return months_diff % _step_months(template) == 0


def _weekly_occurrences_in_period(template: BillTemplate, period: str) -> list[date]:
    """All weekly occurrence dates that fall inside the given month."""
    start = template.start_date
    if start is None:
        return []
    year, month = map(int, period.split("-"))
    first_day = date(year, month, 1)
    last_day = date(year, month, monthrange(year, month)[1])
    if start > last_day:
        return []

    step_days = 7 * template.interval_count
    # First k with start + step*k >= first_day (k >= 0).
    delta = (first_day - start).days
    k = max(0, -(-delta // step_days))
    occurrences: list[date] = []
    current = _step_weeks(start, template.interval_count, k)
    while current <= last_day:
        occurrences.append(current)
        k += 1
        current = _step_weeks(start, template.interval_count, k)
    return occurrences


def _occurrences_in_period(template: BillTemplate, period: str) -> list[date]:
    """Due dates this template's schedule produces inside a "YYYY-MM" period.

    Weekly schedules can yield several occurrences per month; month-anchored
    units yield zero or one; one-off bills yield their single due date in the
    anchor period.
    """
    if template.frequency == BillFrequency.weekly:
        return _weekly_occurrences_in_period(template, period)
    if template.frequency == BillFrequency.one_off:
        anchor = template.start_period or template.created_at.strftime("%Y-%m")
        if period != anchor:
            return []
        return [_due_date_for_period(period, template.due_day)]
    if _bill_active_in_period(template, period):
        return [_due_date_for_period(period, template.due_day)]
    return []


def _first_occurrence_on_or_after(start: date, interval: int, target: date) -> date:
    """First weekly occurrence on/after `target`, or `start` when it is future."""
    if target <= start:
        return start
    step_days = 7 * interval
    delta = (target - start).days
    k = -(-delta // step_days)
    return _step_weeks(start, interval, k)


def backfill_template_instances(
    db: Session, template: BillTemplate, from_period: str, to_period: str
) -> int:
    """Create missing instances for a single template from from_period to to_period inclusive.

    One instance per occurrence (weekly templates may have several per month).
    Returns the number of instances actually inserted (0 when every occurrence
    already has a row, including soft-deleted tombstones). The idempotency key
    is (bill_id, due_date).
    """
    candidate_due_dates: list[date] = []
    period = from_period
    while period <= to_period:
        candidate_due_dates.extend(_occurrences_in_period(template, period))
        period = _add_months(period, 1)

    if not candidate_due_dates:
        return 0

    # Single query for all existing rows — avoids N+1 per occurrence.
    existing_due_dates = {
        row.due_date
        for row in db.query(PaymentInstance.due_date).filter(
            PaymentInstance.bill_id == template.id,
            PaymentInstance.due_date.in_(candidate_due_dates),
        )
    }

    created = 0
    for due_date in candidate_due_dates:
        if due_date in existing_due_dates:
            continue
        db.add(
            PaymentInstance(
                bill_id=template.id,
                period=due_date.strftime("%Y-%m"),
                due_date=due_date,
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
    `(bill_id, due_date)` uniqueness check in `backfill_template_instances`.
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
    """Idempotently seed payment instances for eligible templates in period.

    Weekly templates get one row per occurrence; existence is keyed on
    (bill_id, due_date) ignoring `is_deleted` so tombstones still block.
    One-off bills are included here (their single occurrence) — unlike the
    series generator, which deliberately skips them.
    """
    templates = (
        db.query(BillTemplate)
        .filter(
            BillTemplate.user_id == user_id,
            BillTemplate.is_archived.is_(False),
            BillTemplate.is_paused.is_(False),
        )
        .all()
    )
    for template in templates:
        occurrences = _occurrences_in_period(template, period)
        if not occurrences:
            continue
        existing_due_dates = {
            row.due_date
            for row in db.query(PaymentInstance.due_date).filter(
                PaymentInstance.bill_id == template.id,
                PaymentInstance.due_date.in_(occurrences),
            )
        }
        for due_date in occurrences:
            if due_date in existing_due_dates:
                continue
            db.add(
                PaymentInstance(
                    bill_id=template.id,
                    period=period,
                    due_date=due_date,
                    amount=template.amount,
                    status=PaymentStatus.upcoming,
                )
            )
    if db.new:
        db.commit()


def generate_next_instance(
    db: Session, template: BillTemplate, paid_due_date: date
) -> PaymentInstance | None:
    """Create the next instance after a payment. Idempotent on (bill_id, due_date)."""
    if template.frequency == BillFrequency.one_off:
        return None

    if template.frequency == BillFrequency.weekly:
        if template.start_date is None:
            return None
        next_due_date = paid_due_date + timedelta(days=7 * template.interval_count)
    else:
        next_period = _next_period(
            paid_due_date.strftime("%Y-%m"),
            template.frequency,
            template.interval_count,
        )
        next_due_date = _due_date_for_period(next_period, template.due_day)

    # idempotent: skip if already exists
    existing = (
        db.query(PaymentInstance)
        .filter(
            PaymentInstance.bill_id == template.id,
            PaymentInstance.due_date == next_due_date,
        )
        .first()
    )
    if existing:
        return existing

    instance = PaymentInstance(
        bill_id=template.id,
        period=next_due_date.strftime("%Y-%m"),
        due_date=next_due_date,
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
                PaymentInstance.due_date == next_due_date,
            )
            .first()
        )
    db.refresh(instance)
    return instance


def recompute_weekly_instances(db: Session, template: BillTemplate, today: date) -> int:
    """Re-space future unpaid instances after a weekly schedule change.

    The first future instance moves to the first occurrence on/after `today`
    (or `start_date` when it is still in the future); each following instance
    lands one step later. Paid and soft-deleted rows are untouched. Returns the
    number of rows updated; the caller owns the commit.
    """
    if template.frequency != BillFrequency.weekly or template.start_date is None:
        return 0

    instances = (
        db.query(PaymentInstance)
        .filter(
            PaymentInstance.bill_id == template.id,
            PaymentInstance.status != PaymentStatus.paid,
            PaymentInstance.is_deleted.is_(False),
            PaymentInstance.due_date >= today,
        )
        .order_by(PaymentInstance.due_date, PaymentInstance.id)
        .all()
    )
    if not instances:
        return 0

    first_due = _first_occurrence_on_or_after(
        template.start_date, template.interval_count, today
    )
    for index, instance in enumerate(instances):
        new_due_date = _step_weeks(first_due, template.interval_count, index)
        instance.due_date = new_due_date
        instance.period = new_due_date.strftime("%Y-%m")
    return len(instances)
