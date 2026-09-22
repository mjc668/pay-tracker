"""Tests for app/services/recurrence.py.

Section 1 (below): pure-function parametrized tests — no DB, no fixtures.
Section 2 (below): DB-backed service tests for generate_next_instance
  and ensure_current_period_instances.

Research: context/changes/testing-recurrence-unit/research.md
"""

import types
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError as SAIntegrityError

import app.models.bill  # noqa: F401 — register models with SQLAlchemy's mapper
import app.models.category  # noqa: F401
import app.models.user  # noqa: F401
from app.models.bill import (
    BillFrequency,
    BillTemplate,
    PaymentInstance,
    PaymentStatus,
)
from app.models.category import Category
from app.models.user import User
from app.services.recurrence import (
    _bill_active_in_period,
    _due_date_for_period,
    _first_occurrence_on_or_after,
    _next_period,
    _occurrences_in_period,
    _step_weeks,
    backfill_template_instances,
    ensure_current_period_instances,
    generate_next_instance,
    validate_schedule,
)

# ── Section 1: pure function tests (no DB) ───────────────────────────────────


@pytest.mark.parametrize(
    "period,frequency,interval,expected",
    [
        # monthly — standard and year rollover
        ("2026-01", BillFrequency.monthly, 1, "2026-02"),
        ("2026-12", BillFrequency.monthly, 1, "2027-01"),
        # monthly with intervals (legacy every_2_months/quarterly values)
        ("2026-01", BillFrequency.monthly, 3, "2026-04"),
        ("2026-11", BillFrequency.monthly, 3, "2027-02"),
        ("2026-12", BillFrequency.monthly, 3, "2027-03"),
        ("2026-06", BillFrequency.monthly, 12, "2027-06"),
        # annual — standard and December
        ("2026-06", BillFrequency.annual, 1, "2027-06"),
        ("2026-12", BillFrequency.annual, 1, "2027-12"),
        # annual with intervals
        ("2026-06", BillFrequency.annual, 2, "2028-06"),
        ("2026-01", BillFrequency.annual, 5, "2031-01"),
        # one_off invariant: same period returned unchanged.
        # The guard in generate_next_instance prevents this path from being
        # reached in production — this test documents the invariant so
        # removing that guard produces a visible failure.
        ("2026-06", BillFrequency.one_off, 1, "2026-06"),
    ],
)
def test_next_period(
    period: str, frequency: BillFrequency, interval: int, expected: str
) -> None:
    assert _next_period(period, frequency, interval) == expected


@pytest.mark.parametrize(
    "start,interval,k,expected",
    [
        (date(2026, 1, 5), 1, 0, date(2026, 1, 5)),
        (date(2026, 1, 5), 1, 1, date(2026, 1, 12)),
        (date(2026, 1, 5), 2, 3, date(2026, 2, 16)),
        (date(2026, 1, 5), 4, 2, date(2026, 3, 2)),
    ],
)
def test_step_weeks(start: date, interval: int, k: int, expected: date) -> None:
    assert _step_weeks(start, interval, k) == expected


@pytest.mark.parametrize(
    "start,interval,target,expected",
    [
        # target before/on start → start itself
        (date(2026, 1, 5), 1, date(2026, 1, 1), date(2026, 1, 5)),
        (date(2026, 1, 5), 1, date(2026, 1, 5), date(2026, 1, 5)),
        # target between occurrences → next occurrence
        (date(2026, 1, 5), 1, date(2026, 1, 6), date(2026, 1, 12)),
        (date(2026, 1, 5), 1, date(2026, 2, 1), date(2026, 2, 2)),
        # interval 2: 2026-01-19 is start + 14 days
        (date(2026, 1, 5), 2, date(2026, 1, 19), date(2026, 1, 19)),
        (date(2026, 1, 5), 2, date(2026, 1, 20), date(2026, 2, 2)),
    ],
)
def test_first_occurrence_on_or_after(
    start: date, interval: int, target: date, expected: date
) -> None:
    assert _first_occurrence_on_or_after(start, interval, target) == expected


@pytest.mark.parametrize(
    "period,due_day,expected",
    [
        # Month-end clamping: expected values are hardcoded dates,
        # never recomputed via calendar.monthrange (oracle problem).
        ("2026-02", 31, date(2026, 2, 28)),  # non-leap February
        ("2024-02", 31, date(2024, 2, 29)),  # leap-year February
        ("2026-04", 31, date(2026, 4, 30)),  # April has 30 days
        ("2026-11", 31, date(2026, 11, 30)),  # November has 30 days
        ("2026-01", 31, date(2026, 1, 31)),  # January 31 is valid
        ("2026-12", 31, date(2026, 12, 31)),  # December 31 is valid
        ("2026-06", 15, date(2026, 6, 15)),  # mid-month, no clamping
        ("2026-06", None, date(2026, 6, 1)),  # None defaults to day 1
    ],
)
def test_due_date_for_period(period: str, due_day: int | None, expected: date) -> None:
    assert _due_date_for_period(period, due_day) == expected


def _stub(
    frequency: BillFrequency,
    start_period: str | None,
    created_at: datetime | None = None,
    interval_count: int = 1,
    start_date: date | None = None,
    due_day: int | None = 15,
) -> types.SimpleNamespace:
    """Lightweight BillTemplate stub for pure-function tests."""
    return types.SimpleNamespace(
        frequency=frequency,
        interval_count=interval_count,
        start_period=start_period,
        start_date=start_date,
        due_day=due_day,
        created_at=created_at or datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


@pytest.mark.parametrize(
    "frequency,interval,start_period,target_period,expected",
    [
        # monthly interval 1 is always active (anchor math modulo 1)
        (BillFrequency.monthly, 1, "2026-01", "2026-06", True),
        # monthly interval 2 (legacy every_2_months)
        (BillFrequency.monthly, 2, "2026-01", "2026-03", True),  # +2 months
        (BillFrequency.monthly, 2, "2026-01", "2026-02", False),  # +1 month
        # monthly interval 3 (legacy quarterly)
        (BillFrequency.monthly, 3, "2026-01", "2026-01", True),  # 0 months offset
        (BillFrequency.monthly, 3, "2026-01", "2026-04", True),  # +3 months
        (BillFrequency.monthly, 3, "2026-01", "2026-02", False),  # +1 month
        (BillFrequency.monthly, 3, "2026-01", "2025-12", False),  # before anchor
        # annual
        (BillFrequency.annual, 1, "2026-06", "2027-06", True),  # +12 months
        (BillFrequency.annual, 1, "2026-06", "2027-05", False),  # +11 months
        (BillFrequency.annual, 2, "2026-06", "2028-06", True),  # +24 months
        (BillFrequency.annual, 2, "2026-06", "2027-06", False),  # +12 months
        # weekly is occurrence-based → never active via this helper
        (BillFrequency.weekly, 1, "2026-01", "2026-01", False),
        # one_off: always inactive (fallthrough → False)
        (BillFrequency.one_off, 1, "2026-01", "2026-01", False),
    ],
)
def test_bill_active_in_period(
    frequency: BillFrequency,
    interval: int,
    start_period: str,
    target_period: str,
    expected: bool,
) -> None:
    template = _stub(frequency, start_period, interval_count=interval)
    assert _bill_active_in_period(template, target_period) == expected


def test_bill_active_in_period_created_at_fallback() -> None:
    """start_period=None falls back to created_at.strftime('%Y-%m') as anchor.

    This covers the backward-compat path for rows that predate the
    start_period column. created_at=2026-01-15 → anchor "2026-01".
    """
    template = _stub(
        BillFrequency.monthly,
        start_period=None,
        created_at=datetime(2026, 1, 15, tzinfo=timezone.utc),
        interval_count=3,
    )
    # +3 months from anchor "2026-01" → active
    assert _bill_active_in_period(template, "2026-04") is True
    # +1 month → inactive
    assert _bill_active_in_period(template, "2026-02") is False


# ── _occurrences_in_period ───────────────────────────────────────────────────


@pytest.mark.parametrize(
    "start_date,interval,period,expected",
    [
        # interval 1, Monday anchor: Jan and Feb 2026, plus a 5-Monday month
        (
            date(2026, 1, 5),
            1,
            "2026-01",
            [date(2026, 1, 5), date(2026, 1, 12), date(2026, 1, 19), date(2026, 1, 26)],
        ),
        (
            date(2026, 1, 5),
            1,
            "2026-02",
            [date(2026, 2, 2), date(2026, 2, 9), date(2026, 2, 16), date(2026, 2, 23)],
        ),
        (
            date(2026, 1, 5),
            1,
            "2026-03",
            [
                date(2026, 3, 2),
                date(2026, 3, 9),
                date(2026, 3, 16),
                date(2026, 3, 23),
                date(2026, 3, 30),
            ],
        ),
        # interval 2
        (date(2026, 1, 5), 2, "2026-01", [date(2026, 1, 5), date(2026, 1, 19)]),
        (date(2026, 1, 5), 2, "2026-02", [date(2026, 2, 2), date(2026, 2, 16)]),
        # anchor inside the month, mid-week
        (
            date(2026, 2, 10),
            1,
            "2026-02",
            [date(2026, 2, 10), date(2026, 2, 17), date(2026, 2, 24)],
        ),
        # before the anchor month → nothing
        (date(2026, 2, 10), 1, "2026-01", []),
    ],
)
def test_occurrences_in_period_weekly(
    start_date: date, interval: int, period: str, expected: list[date]
) -> None:
    template = _stub(
        BillFrequency.weekly,
        start_period=start_date.strftime("%Y-%m"),
        interval_count=interval,
        start_date=start_date,
        due_day=None,
    )
    assert _occurrences_in_period(template, period) == expected


def test_occurrences_in_period_weekly_without_start_date() -> None:
    template = _stub(BillFrequency.weekly, "2026-01", due_day=None)
    assert _occurrences_in_period(template, "2026-01") == []


@pytest.mark.parametrize(
    "frequency,interval,start_period,due_day,period,expected",
    [
        (BillFrequency.monthly, 1, "2026-01", 15, "2026-02", [date(2026, 2, 15)]),
        (BillFrequency.monthly, 2, "2026-01", 15, "2026-02", []),
        (BillFrequency.monthly, 2, "2026-01", 15, "2026-03", [date(2026, 3, 15)]),
        # month-end clamping
        (BillFrequency.monthly, 1, "2026-01", 31, "2026-02", [date(2026, 2, 28)]),
        (BillFrequency.annual, 1, "2026-06", 10, "2027-06", [date(2027, 6, 10)]),
        (BillFrequency.annual, 1, "2026-06", 10, "2027-05", []),
        # one-off bills have exactly one occurrence, in their anchor period
        (BillFrequency.one_off, 1, "2026-01", 15, "2026-01", [date(2026, 1, 15)]),
        (BillFrequency.one_off, 1, "2026-01", 15, "2026-02", []),
    ],
)
def test_occurrences_in_period_month_anchored(
    frequency: BillFrequency,
    interval: int,
    start_period: str,
    due_day: int,
    period: str,
    expected: list[date],
) -> None:
    template = _stub(frequency, start_period, interval_count=interval, due_day=due_day)
    assert _occurrences_in_period(template, period) == expected


@pytest.mark.parametrize(
    "frequency,interval,start_date,expected_error",
    [
        (BillFrequency.monthly, 1, None, None),
        (BillFrequency.monthly, 12, None, None),
        (BillFrequency.monthly, 13, None, "between 1 and 12"),
        (BillFrequency.monthly, 0, None, "between 1 and 12"),
        (BillFrequency.weekly, 4, date(2026, 1, 5), None),
        (BillFrequency.weekly, 5, date(2026, 1, 5), "between 1 and 4"),
        (BillFrequency.weekly, 1, None, "require start_date"),
        (BillFrequency.annual, 5, None, None),
        (BillFrequency.annual, 6, None, "between 1 and 5"),
        # one_off intervals are normalized by callers before validation
        (BillFrequency.one_off, 1, None, None),
    ],
)
def test_validate_schedule(
    frequency: BillFrequency,
    interval: int,
    start_date: date | None,
    expected_error: str | None,
) -> None:
    error = validate_schedule(frequency, interval, start_date)
    if expected_error is None:
        assert error is None
    else:
        assert error is not None
        assert expected_error in error


# ── Section 2: DB-backed service tests ──────────────────────────────────────


def _make_user(db, email: str = "u@test.com") -> User:
    user = User(email=email, password_hash="x")
    db.add(user)
    db.flush()
    return user


def _make_bill(
    db,
    user_id: int,
    *,
    frequency: BillFrequency = BillFrequency.monthly,
    interval_count: int = 1,
    start_date: date | None = None,
    due_day: int | None = 15,
    amount: Decimal = Decimal("100.00"),
    start_period: str = "2026-01",
    is_paused: bool = False,
    is_archived: bool = False,
) -> BillTemplate:
    category = Category(user_id=user_id, key="other")
    db.add(category)
    db.flush()
    bill = BillTemplate(
        name="Test Bill",
        frequency=frequency,
        interval_count=interval_count,
        start_date=start_date,
        amount=amount,
        currency="PLN",
        due_day=due_day,
        start_period=start_period,
        is_paused=is_paused,
        is_archived=is_archived,
        category_id=category.id,
        user_id=user_id,
    )
    db.add(bill)
    db.flush()
    return bill


def _make_instance(
    db,
    bill_id: int,
    period: str,
    *,
    due_date: date | None = None,
    is_deleted: bool = False,
) -> PaymentInstance:
    year, month = int(period[:4]), int(period[5:])
    inst = PaymentInstance(
        bill_id=bill_id,
        period=period,
        due_date=due_date or date(year, month, 1),
        amount=Decimal("100.00"),
        status=PaymentStatus.upcoming,
        is_deleted=is_deleted,
    )
    db.add(inst)
    db.flush()
    return inst


# ── generate_next_instance ───────────────────────────────────────────────────


def test_generate_next_instance_monthly_creates_next_period(db_session) -> None:
    user = _make_user(db_session)
    bill = _make_bill(
        db_session,
        user.id,
        frequency=BillFrequency.monthly,
        due_day=15,
        start_period="2026-05",
    )
    bill_id = bill.id
    db_session.commit()

    bill = db_session.get(BillTemplate, bill_id)
    instance = generate_next_instance(db_session, bill, date(2026, 5, 15))

    assert instance is not None
    assert instance.period == "2026-06"
    assert instance.status == PaymentStatus.upcoming
    assert instance.due_date == date(2026, 6, 15)


def test_generate_next_instance_monthly_interval_three(db_session) -> None:
    user = _make_user(db_session)
    bill = _make_bill(
        db_session,
        user.id,
        frequency=BillFrequency.monthly,
        interval_count=3,
        due_day=15,
        start_period="2026-05",
    )
    bill_id = bill.id
    db_session.commit()

    bill = db_session.get(BillTemplate, bill_id)
    instance = generate_next_instance(db_session, bill, date(2026, 5, 15))

    assert instance is not None
    assert instance.period == "2026-08"
    assert instance.due_date == date(2026, 8, 15)


def test_generate_next_instance_annual_interval_two(db_session) -> None:
    user = _make_user(db_session)
    bill = _make_bill(
        db_session,
        user.id,
        frequency=BillFrequency.annual,
        interval_count=2,
        due_day=15,
        start_period="2026-05",
    )
    bill_id = bill.id
    db_session.commit()

    bill = db_session.get(BillTemplate, bill_id)
    instance = generate_next_instance(db_session, bill, date(2026, 5, 15))

    assert instance is not None
    assert instance.period == "2028-05"
    assert instance.due_date == date(2028, 5, 15)


def test_generate_next_instance_weekly(db_session) -> None:
    user = _make_user(db_session)
    bill = _make_bill(
        db_session,
        user.id,
        frequency=BillFrequency.weekly,
        start_date=date(2026, 5, 4),
        due_day=None,
        start_period="2026-05",
    )
    bill_id = bill.id
    db_session.commit()

    bill = db_session.get(BillTemplate, bill_id)
    instance = generate_next_instance(db_session, bill, date(2026, 5, 4))

    assert instance is not None
    assert instance.due_date == date(2026, 5, 11)
    assert instance.period == "2026-05"


def test_generate_next_instance_weekly_interval_two(db_session) -> None:
    user = _make_user(db_session)
    bill = _make_bill(
        db_session,
        user.id,
        frequency=BillFrequency.weekly,
        interval_count=2,
        start_date=date(2026, 5, 4),
        due_day=None,
        start_period="2026-05",
    )
    bill_id = bill.id
    db_session.commit()

    bill = db_session.get(BillTemplate, bill_id)
    instance = generate_next_instance(db_session, bill, date(2026, 5, 4))

    assert instance is not None
    assert instance.due_date == date(2026, 5, 18)


def test_generate_next_instance_one_off_returns_none(db_session) -> None:
    user = _make_user(db_session)
    bill = _make_bill(db_session, user.id, frequency=BillFrequency.one_off)
    bill_id = bill.id
    db_session.commit()

    bill = db_session.get(BillTemplate, bill_id)
    result = generate_next_instance(db_session, bill, date(2026, 5, 15))

    assert result is None
    assert db_session.query(PaymentInstance).filter_by(bill_id=bill_id).count() == 0


def test_generate_next_instance_idempotent(db_session) -> None:
    user = _make_user(db_session)
    bill = _make_bill(db_session, user.id)
    bill_id = bill.id
    db_session.commit()

    # First call creates the instance for "2026-06"
    bill = db_session.get(BillTemplate, bill_id)
    first = generate_next_instance(db_session, bill, date(2026, 5, 15))
    first_id = first.id

    # Second call must return the existing instance — no duplicate
    bill = db_session.get(BillTemplate, bill_id)
    second = generate_next_instance(db_session, bill, date(2026, 5, 15))

    assert second.id == first_id
    count = (
        db_session.query(PaymentInstance)
        .filter_by(bill_id=bill_id, due_date=date(2026, 6, 15))
        .count()
    )
    assert count == 1


def test_generate_next_instance_copies_amount_and_due_date(db_session) -> None:
    user = _make_user(db_session)
    # due_day=31 in June clamps to 30
    bill = _make_bill(
        db_session,
        user.id,
        frequency=BillFrequency.monthly,
        due_day=31,
        amount=Decimal("150.00"),
    )
    bill_id = bill.id
    db_session.commit()

    bill = db_session.get(BillTemplate, bill_id)
    instance = generate_next_instance(db_session, bill, date(2026, 5, 31))

    assert instance.amount == Decimal("150.00")
    assert instance.due_date == date(2026, 6, 30)  # June has 30 days


def test_generate_next_instance_returns_tombstone_for_same_due_date(
    db_session,
) -> None:
    """A soft-deleted row on the next due date blocks re-creation."""
    user = _make_user(db_session)
    bill = _make_bill(
        db_session,
        user.id,
        frequency=BillFrequency.weekly,
        start_date=date(2026, 5, 4),
        due_day=None,
        start_period="2026-05",
    )
    bill_id = bill.id
    _make_instance(
        db_session, bill_id, "2026-05", due_date=date(2026, 5, 11), is_deleted=True
    )
    db_session.commit()

    bill = db_session.get(BillTemplate, bill_id)
    result = generate_next_instance(db_session, bill, date(2026, 5, 4))

    assert result is not None
    assert result.due_date == date(2026, 5, 11)
    assert result.is_deleted is True
    assert db_session.query(PaymentInstance).filter_by(bill_id=bill_id).count() == 1


def test_generate_next_instance_integrity_error_fallback(
    db_session, db_sessionmaker
) -> None:
    """Race-condition path: concurrent insert causes IntegrityError → rollback → return winner.

    Simulated by: (1) mocking the pre-check query to return None (race window where
    our session checked before the winner committed), (2) mocking commit to raise
    IntegrityError, and (3) pre-committing the winner via a separate session so the
    fallback re-query finds it.
    """
    user = _make_user(db_session)
    bill = _make_bill(db_session, user.id, start_period="2026-05")
    bill_id = bill.id
    db_session.commit()

    # "Winner" session commits the next-period row first
    winner_session = db_sessionmaker()
    winner = PaymentInstance(
        bill_id=bill_id,
        period="2026-06",
        due_date=date(2026, 6, 15),
        amount=Decimal("100.00"),
        status=PaymentStatus.upcoming,
    )
    winner_session.add(winner)
    winner_session.commit()
    winner_id = winner.id
    winner_session.close()

    bill = db_session.get(BillTemplate, bill_id)

    # Simulate race window: pre-check sees nothing, commit then fails
    real_query = db_session.query
    pre_check_intercepted = [False]

    def mock_query(model):
        if model is PaymentInstance and not pre_check_intercepted[0]:
            pre_check_intercepted[0] = True
            stub = MagicMock()
            stub.filter.return_value = stub
            stub.first.return_value = None
            return stub
        return real_query(model)

    commit_raised = [False]

    def mock_commit():
        if not commit_raised[0]:
            commit_raised[0] = True
            raise SAIntegrityError("insert", {}, Exception("unique violation"))

    with (
        patch.object(db_session, "query", side_effect=mock_query),
        patch.object(db_session, "commit", side_effect=mock_commit),
    ):
        result = generate_next_instance(db_session, bill, date(2026, 5, 15))

    assert result is not None
    assert result.id == winner_id


# ── ensure_current_period_instances ──────────────────────────────────────────


def test_ensure_creates_instance_for_active_template(db_session) -> None:
    user = _make_user(db_session)
    _make_bill(db_session, user.id, frequency=BillFrequency.monthly)
    user_id = user.id
    db_session.commit()

    ensure_current_period_instances(db_session, "2026-06", user_id)

    assert db_session.query(PaymentInstance).filter_by(period="2026-06").count() == 1


def test_ensure_skips_archived_template(db_session) -> None:
    user = _make_user(db_session)
    _make_bill(db_session, user.id, frequency=BillFrequency.monthly, is_archived=True)
    user_id = user.id
    db_session.commit()

    ensure_current_period_instances(db_session, "2026-06", user_id)

    assert db_session.query(PaymentInstance).count() == 0


def test_ensure_skips_paused_template(db_session) -> None:
    user = _make_user(db_session)
    _make_bill(db_session, user.id, frequency=BillFrequency.monthly, is_paused=True)
    user_id = user.id
    db_session.commit()

    ensure_current_period_instances(db_session, "2026-06", user_id)

    assert db_session.query(PaymentInstance).count() == 0


def test_ensure_creates_one_off_only_in_anchor_period(db_session) -> None:
    user = _make_user(db_session)
    _make_bill(
        db_session, user.id, frequency=BillFrequency.one_off, start_period="2026-01"
    )
    user_id = user.id
    db_session.commit()

    # A different period produces nothing...
    ensure_current_period_instances(db_session, "2026-06", user_id)
    assert db_session.query(PaymentInstance).count() == 0

    # ...the anchor period materializes the single occurrence.
    ensure_current_period_instances(db_session, "2026-01", user_id)
    instances = db_session.query(PaymentInstance).all()
    assert len(instances) == 1
    assert instances[0].due_date == date(2026, 1, 15)


def test_ensure_skips_inactive_period(db_session) -> None:
    user = _make_user(db_session)
    # Monthly interval 2 from "2026-01": active in 2026-01, 2026-03, 2026-05 ...
    _make_bill(
        db_session,
        user.id,
        frequency=BillFrequency.monthly,
        interval_count=2,
        start_period="2026-01",
    )
    user_id = user.id
    db_session.commit()

    # "2026-02" is 1 month after anchor → not a cycle
    ensure_current_period_instances(db_session, "2026-02", user_id)

    assert db_session.query(PaymentInstance).count() == 0


def test_ensure_idempotent(db_session) -> None:
    user = _make_user(db_session)
    _make_bill(db_session, user.id, frequency=BillFrequency.monthly)
    user_id = user.id
    db_session.commit()

    ensure_current_period_instances(db_session, "2026-06", user_id)

    # Second call must not produce a duplicate
    ensure_current_period_instances(db_session, "2026-06", user_id)

    assert db_session.query(PaymentInstance).filter_by(period="2026-06").count() == 1


def test_ensure_respects_soft_delete_tombstone(db_session) -> None:
    """A soft-deleted instance (is_deleted=True) acts as a tombstone.

    ensure_current_period_instances must NOT re-generate an occurrence whose
    (bill_id, due_date) already has a row, regardless of is_deleted.
    """
    user = _make_user(db_session)
    bill = _make_bill(db_session, user.id, frequency=BillFrequency.monthly, due_day=15)
    _make_instance(
        db_session, bill.id, "2026-06", due_date=date(2026, 6, 15), is_deleted=True
    )
    user_id = user.id
    db_session.commit()

    ensure_current_period_instances(db_session, "2026-06", user_id)

    # Still exactly 1 row — the tombstone blocked re-creation
    assert db_session.query(PaymentInstance).filter_by(period="2026-06").count() == 1


def test_ensure_weekly_creates_all_occurrences(db_session) -> None:
    user = _make_user(db_session)
    _make_bill(
        db_session,
        user.id,
        frequency=BillFrequency.weekly,
        start_date=date(2026, 6, 1),
        due_day=None,
        start_period="2026-06",
    )
    user_id = user.id
    db_session.commit()

    ensure_current_period_instances(db_session, "2026-06", user_id)

    due_dates = {
        row.due_date
        for row in db_session.query(PaymentInstance).filter_by(period="2026-06")
    }
    assert due_dates == {
        date(2026, 6, 1),
        date(2026, 6, 8),
        date(2026, 6, 15),
        date(2026, 6, 22),
        date(2026, 6, 29),
    }


def test_ensure_weekly_tombstone_blocks_single_occurrence(db_session) -> None:
    user = _make_user(db_session)
    bill = _make_bill(
        db_session,
        user.id,
        frequency=BillFrequency.weekly,
        start_date=date(2026, 6, 1),
        due_day=None,
        start_period="2026-06",
    )
    _make_instance(
        db_session, bill.id, "2026-06", due_date=date(2026, 6, 8), is_deleted=True
    )
    user_id = user.id
    db_session.commit()

    ensure_current_period_instances(db_session, "2026-06", user_id)

    due_dates = {
        row.due_date
        for row in db_session.query(PaymentInstance).filter_by(period="2026-06")
    }
    assert due_dates == {
        date(2026, 6, 1),
        date(2026, 6, 8),
        date(2026, 6, 15),
        date(2026, 6, 22),
        date(2026, 6, 29),
    }


def test_ensure_scoped_to_user(db_session) -> None:
    user_a = _make_user(db_session, "a@test.com")
    user_b = _make_user(db_session, "b@test.com")
    _make_bill(db_session, user_a.id, frequency=BillFrequency.monthly)
    _make_bill(db_session, user_b.id, frequency=BillFrequency.monthly)
    user_a_id = user_a.id
    user_b_id = user_b.id
    db_session.commit()

    # Seed only for user_a
    ensure_current_period_instances(db_session, "2026-06", user_a_id)

    a_count = (
        db_session.query(PaymentInstance)
        .join(BillTemplate)
        .filter(
            BillTemplate.user_id == user_a_id,
            PaymentInstance.period == "2026-06",
        )
        .count()
    )
    b_count = (
        db_session.query(PaymentInstance)
        .join(BillTemplate)
        .filter(
            BillTemplate.user_id == user_b_id,
            PaymentInstance.period == "2026-06",
        )
        .count()
    )
    assert a_count == 1
    assert b_count == 0


# ── backfill_template_instances ──────────────────────────────────────────────


def test_backfill_creates_instance_for_each_active_period(db_session) -> None:
    """Monthly bill with start_period 3 months back → 3 instances seeded."""
    user = _make_user(db_session)
    bill = _make_bill(
        db_session,
        user.id,
        frequency=BillFrequency.monthly,
        due_day=10,
        start_period="2026-01",
    )
    db_session.commit()

    backfill_template_instances(db_session, bill, "2026-01", "2026-03")

    count = db_session.query(PaymentInstance).filter_by(bill_id=bill.id).count()
    assert count == 3

    periods = {
        row.period
        for row in db_session.query(PaymentInstance).filter_by(bill_id=bill.id)
    }
    assert periods == {"2026-01", "2026-02", "2026-03"}


def test_backfill_is_idempotent(db_session) -> None:
    """Running backfill twice over the same range must not create duplicates."""
    user = _make_user(db_session)
    bill = _make_bill(
        db_session,
        user.id,
        frequency=BillFrequency.monthly,
        start_period="2026-01",
    )
    db_session.commit()

    backfill_template_instances(db_session, bill, "2026-01", "2026-03")
    backfill_template_instances(db_session, bill, "2026-01", "2026-03")

    assert db_session.query(PaymentInstance).filter_by(bill_id=bill.id).count() == 3


def test_backfill_skips_inactive_periods_for_monthly_interval_three(
    db_session,
) -> None:
    """Interval-3 bill anchored at 2026-01, range 2026-01..2026-06 → 2 instances."""
    user = _make_user(db_session)
    bill = _make_bill(
        db_session,
        user.id,
        frequency=BillFrequency.monthly,
        interval_count=3,
        start_period="2026-01",
    )
    db_session.commit()

    backfill_template_instances(db_session, bill, "2026-01", "2026-06")

    periods = {
        row.period
        for row in db_session.query(PaymentInstance).filter_by(bill_id=bill.id)
    }
    assert periods == {"2026-01", "2026-04"}


def test_backfill_creates_weekly_occurrences(db_session) -> None:
    """Weekly bill anchored 2026-01-05: 4 January + 4 February occurrences."""
    user = _make_user(db_session)
    bill = _make_bill(
        db_session,
        user.id,
        frequency=BillFrequency.weekly,
        start_date=date(2026, 1, 5),
        due_day=None,
        start_period="2026-01",
    )
    db_session.commit()

    created = backfill_template_instances(db_session, bill, "2026-01", "2026-02")

    assert created == 8
    due_dates = {
        row.due_date
        for row in db_session.query(PaymentInstance).filter_by(bill_id=bill.id)
    }
    assert due_dates == {
        date(2026, 1, 5),
        date(2026, 1, 12),
        date(2026, 1, 19),
        date(2026, 1, 26),
        date(2026, 2, 2),
        date(2026, 2, 9),
        date(2026, 2, 16),
        date(2026, 2, 23),
    }


def test_backfill_weekly_tombstone_blocks_one_occurrence(db_session) -> None:
    user = _make_user(db_session)
    bill = _make_bill(
        db_session,
        user.id,
        frequency=BillFrequency.weekly,
        start_date=date(2026, 1, 5),
        due_day=None,
        start_period="2026-01",
    )
    _make_instance(
        db_session, bill.id, "2026-01", due_date=date(2026, 1, 12), is_deleted=True
    )
    db_session.commit()

    created = backfill_template_instances(db_session, bill, "2026-01", "2026-01")

    assert created == 3
    assert db_session.query(PaymentInstance).filter_by(bill_id=bill.id).count() == 4
