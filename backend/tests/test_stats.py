"""Integration tests for GET /stats/overview (dashboard stats).

Instances are inserted directly (via a DB session) so that periods and due
dates are deterministic regardless of the calendar day CI runs on.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.bill import BillTemplate, PaymentInstance, PaymentStatus
from tests.conftest import auth, register_and_login

_BILL = {
    "name": "Electricity",
    "category": "utilities",
    "frequency": "monthly",
    "amount": "100.00",
    "currency": "PLN",
    "due_day": 15,
    "notes": None,
    "is_paused": False,
}


def _create_bill(client: TestClient, token: str, overrides: dict | None = None) -> int:
    payload = {**_BILL, **(overrides or {})}
    r = client.post("/bills", json=payload, headers=auth(token))
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _insert_instance(
    db: Session,
    bill_id: int,
    *,
    period: str,
    due_date: date,
    amount: str = "100.00",
    status: PaymentStatus = PaymentStatus.upcoming,
    paid_amount: str | None = None,
    is_deleted: bool = False,
) -> PaymentInstance:
    inst = PaymentInstance(
        bill_id=bill_id,
        period=period,
        due_date=due_date,
        amount=Decimal(amount),
        status=status,
        paid_amount=Decimal(paid_amount) if paid_amount is not None else None,
        is_deleted=is_deleted,
    )
    db.add(inst)
    db.commit()
    db.refresh(inst)
    return inst


def _pay(
    client: TestClient,
    token: str,
    instance_id: int,
    amount: str,
    *,
    paid_on: str | None = None,
) -> dict:
    r = client.post(
        f"/bills/payments/{instance_id}/payments",
        json={"amount": amount, "paid_on": paid_on},
        headers=auth(token),
    )
    assert r.status_code == 200, r.text
    return r.json()


def _overview(client: TestClient, token: str, query: str = "") -> dict:
    r = client.get(f"/stats/overview{query}", headers=auth(token))
    assert r.status_code == 200, r.text
    return r.json()


def _dec(value: object) -> Decimal:
    return Decimal(str(value))


def _shift(period: str, delta: int) -> str:
    year, month = map(int, period.split("-"))
    total = year * 12 + month - 1 + delta
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


def _day_in(period: str, day: int) -> date:
    year, month = map(int, period.split("-"))
    return date(year, month, day)


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------


def test_summary_math_full_partial_and_overdue(client_db):
    client, db = client_db
    token = register_and_login(client, "stats_summary@test.com")
    today = date.today()
    period = today.strftime("%Y-%m")

    full_bill = _create_bill(client, token, {"name": "Full", "frequency": "one_off"})
    partial_bill = _create_bill(client, token, {"name": "Partial"})
    overdue_bill = _create_bill(client, token, {"name": "Overdue"})

    full = _insert_instance(
        db,
        full_bill,
        period=period,
        due_date=today + timedelta(days=5),
        amount="100.00",
    )
    partial = _insert_instance(
        db,
        partial_bill,
        period=period,
        due_date=today + timedelta(days=6),
        amount="200.00",
    )
    _insert_instance(
        db,
        overdue_bill,
        period=period,
        due_date=today - timedelta(days=3),
        amount="300.00",
        status=PaymentStatus.overdue,
    )

    _pay(client, token, full.id, "100.00", paid_on=today.isoformat())
    _pay(client, token, partial.id, "50.00", paid_on=today.isoformat())

    summary = _overview(client, token)["summary"]
    assert _dec(summary["due_total"]) == Decimal("600.00")
    assert _dec(summary["paid_total"]) == Decimal("150.00")
    assert _dec(summary["remaining_total"]) == Decimal("450.00")
    assert summary["total_count"] == 3
    assert summary["paid_count"] == 1
    assert summary["upcoming_count"] == 1
    assert summary["overdue_count"] == 1
    assert _dec(summary["overdue_total"]) == Decimal("300.00")


def test_summary_scoped_to_requested_month(client_db):
    client, db = client_db
    token = register_and_login(client, "stats_month@test.com")
    today = date.today()
    current = today.strftime("%Y-%m")
    previous = _shift(current, -1)

    bill_id = _create_bill(client, token)
    _insert_instance(
        db,
        bill_id,
        period=previous,
        due_date=_day_in(previous, 5),
        amount="100.00",
    )
    _insert_instance(
        db,
        bill_id,
        period=current,
        due_date=today + timedelta(days=4),
        amount="200.00",
    )

    data = _overview(client, token, f"?month={previous}&months=1")
    assert data["month"] == previous
    assert data["months"] == 1
    assert _dec(data["summary"]["due_total"]) == Decimal("100.00")
    assert data["summary"]["total_count"] == 1
    assert [p["period"] for p in data["trend"]] == [previous]
    assert _dec(data["trend"][0]["paid_total"]) == Decimal("0")
    assert _dec(data["trend"][0]["due_total"]) == Decimal("100.00")


# ---------------------------------------------------------------------------
# Primary currency
# ---------------------------------------------------------------------------


def test_primary_currency_dominant_and_filters_stats(client_db):
    client, db = client_db
    token = register_and_login(client, "stats_currency@test.com")
    today = date.today()
    period = today.strftime("%Y-%m")

    _create_bill(client, token, {"name": "PLN one", "currency": "PLN"})
    pln = _create_bill(client, token, {"name": "PLN two", "currency": "PLN"})
    eur = _create_bill(client, token, {"name": "EUR", "currency": "EUR"})

    _insert_instance(
        db, pln, period=period, due_date=today + timedelta(days=3), amount="80.00"
    )
    _insert_instance(
        db, eur, period=period, due_date=today + timedelta(days=3), amount="999.00"
    )

    data = _overview(client, token)
    assert data["currency"] == "PLN"
    assert data["other_currencies"] == ["EUR"]
    assert _dec(data["summary"]["due_total"]) == Decimal("80.00")
    assert _dec(data["trend"][-1]["due_total"]) == Decimal("80.00")


def test_primary_currency_tie_breaks_alphabetically(client):
    token = register_and_login(client, "stats_tie@test.com")
    _create_bill(client, token, {"name": "PLN", "currency": "PLN"})
    _create_bill(client, token, {"name": "EUR", "currency": "EUR"})

    data = _overview(client, token)
    assert data["currency"] == "EUR"
    assert data["other_currencies"] == ["PLN"]


def test_archived_templates_ignored_for_currency(client):
    token = register_and_login(client, "stats_archived@test.com")
    eur_a = _create_bill(client, token, {"name": "Archived EUR A", "currency": "EUR"})
    eur_b = _create_bill(client, token, {"name": "Archived EUR B", "currency": "EUR"})
    _create_bill(client, token, {"name": "Active PLN", "currency": "PLN"})

    for bill_id in (eur_a, eur_b):
        r = client.post(f"/bills/{bill_id}/archive", headers=auth(token))
        assert r.status_code == 204, r.text

    data = _overview(client, token)
    assert data["currency"] == "PLN"
    assert data["other_currencies"] == []


# ---------------------------------------------------------------------------
# Trend
# ---------------------------------------------------------------------------


def test_trend_buckets_payments_by_paid_on_oldest_first(client_db):
    client, db = client_db
    token = register_and_login(client, "stats_trend@test.com")
    today = date.today()
    current = today.strftime("%Y-%m")
    previous = _shift(current, -1)

    bill_id = _create_bill(client, token)
    prev_inst = _insert_instance(
        db, bill_id, period=previous, due_date=_day_in(previous, 5), amount="100.00"
    )
    cur_inst = _insert_instance(
        db,
        bill_id,
        period=current,
        due_date=today + timedelta(days=5),
        amount="200.00",
    )

    # Recorded later but dated in the previous month → previous month bucket.
    _pay(
        client,
        token,
        prev_inst.id,
        "40.00",
        paid_on=_day_in(previous, 10).isoformat(),
    )
    _pay(client, token, cur_inst.id, "60.00", paid_on=today.isoformat())

    data = _overview(client, token, "?months=3")
    assert data["months"] == 3
    assert [p["period"] for p in data["trend"]] == [
        _shift(current, -2),
        previous,
        current,
    ]

    by_period = {p["period"]: p for p in data["trend"]}
    assert _dec(by_period[_shift(current, -2)]["paid_total"]) == Decimal("0")
    assert _dec(by_period[_shift(current, -2)]["due_total"]) == Decimal("0")
    assert _dec(by_period[previous]["paid_total"]) == Decimal("40.00")
    assert _dec(by_period[previous]["due_total"]) == Decimal("100.00")
    assert _dec(by_period[current]["paid_total"]) == Decimal("60.00")
    assert _dec(by_period[current]["due_total"]) == Decimal("200.00")


# ---------------------------------------------------------------------------
# Forecast
# ---------------------------------------------------------------------------


def test_forecast_six_points_oldest_first_from_requested_month(client):
    token = register_and_login(client, "stats_forecast_window@test.com")

    data = _overview(client, token, "?month=2026-01&months=1")
    assert data["months"] == 1
    assert [point["period"] for point in data["forecast"]] == [
        "2026-02",
        "2026-03",
        "2026-04",
        "2026-05",
        "2026-06",
        "2026-07",
    ]
    assert all(_dec(point["expected_total"]) == 0 for point in data["forecast"])


def test_forecast_monthly_contributes_every_month_and_ignores_instances(client_db):
    client, db = client_db
    token = register_and_login(client, "stats_forecast_monthly@test.com")
    current = date.today().strftime("%Y-%m")

    bill_id = _create_bill(client, token, {"amount": "100.00"})
    # A pre-existing (or generated) instance must not subtract from the expectation.
    _insert_instance(
        db,
        bill_id,
        period=_shift(current, 1),
        due_date=_day_in(_shift(current, 1), 15),
        amount="100.00",
    )

    forecast = _overview(client, token)["forecast"]
    assert [point["period"] for point in forecast] == [
        _shift(current, offset) for offset in range(1, 7)
    ]
    assert all(_dec(point["expected_total"]) == Decimal("100.00") for point in forecast)


def test_forecast_intervals_and_annual_only_on_active_periods(client_db):
    client, db = client_db
    token = register_and_login(client, "stats_forecast_cycle@test.com")
    current = date.today().strftime("%Y-%m")

    _create_bill(
        client,
        token,
        {"name": "Quarterly", "interval_count": 3, "amount": "30.00"},
    )
    annual_id = _create_bill(
        client, token, {"name": "Annual", "frequency": "annual", "amount": "120.00"}
    )
    # Annual bills created through the API are anchored in the future; move the
    # anchor back 11 months so '+1' is a recurrence boundary.
    db.query(BillTemplate).filter(BillTemplate.id == annual_id).update(
        {"start_period": _shift(current, -11)}
    )
    db.commit()

    forecast = _overview(client, token)["forecast"]
    assert [point["period"] for point in forecast] == [
        _shift(current, offset) for offset in range(1, 7)
    ]
    expected = {
        1: Decimal("120.00"),  # annual boundary
        2: Decimal("0"),
        3: Decimal("30.00"),  # interval-3 (anchor +3)
        4: Decimal("0"),
        5: Decimal("0"),
        6: Decimal("30.00"),  # interval-3 (anchor +6)
    }
    for offset, value in expected.items():
        point = forecast[offset - 1]
        assert _dec(point["expected_total"]) == value, point


def test_forecast_counts_weekly_occurrences_per_month(client_db):
    """A weekly bill contributes amount × occurrences in each forecast month."""
    client, db = client_db
    token = register_and_login(client, "stats_forecast_weekly@test.com")
    current = date.today().strftime("%Y-%m")
    start = date(int(current[:4]), int(current[5:]), 1)

    _create_bill(
        client,
        token,
        {
            "name": "Weekly",
            "frequency": "weekly",
            "start_date": start.isoformat(),
            "amount": "10.00",
            "due_day": None,
        },
    )

    forecast = _overview(client, token)["forecast"]
    assert [point["period"] for point in forecast] == [
        _shift(current, offset) for offset in range(1, 7)
    ]

    for point in forecast:
        year, month = map(int, point["period"].split("-"))
        month_start = date(year, month, 1)
        # Independent oracle: count 7-day steps that land in this month.
        occurrences = 0
        cursor = start
        while cursor < month_start:
            cursor += timedelta(days=7)
        while cursor.strftime("%Y-%m") == point["period"]:
            occurrences += 1
            cursor += timedelta(days=7)
        assert _dec(point["expected_total"]) == Decimal("10.00") * occurrences, point


def test_forecast_excludes_paused_and_archived(client_db):
    client, db = client_db
    token = register_and_login(client, "stats_forecast_excluded@test.com")
    current = date.today().strftime("%Y-%m")

    _create_bill(client, token, {"name": "Active", "amount": "10.00"})
    _create_bill(
        client, token, {"name": "Paused", "amount": "100.00", "is_paused": True}
    )
    archived = _create_bill(client, token, {"name": "Archived", "amount": "1000.00"})

    r = client.post(f"/bills/{archived}/archive", headers=auth(token))
    assert r.status_code == 204, r.text

    forecast = _overview(client, token)["forecast"]
    assert [point["period"] for point in forecast] == [
        _shift(current, offset) for offset in range(1, 7)
    ]
    assert all(_dec(point["expected_total"]) == Decimal("10.00") for point in forecast)


def test_forecast_includes_one_off_in_its_month(client_db):
    client, db = client_db
    token = register_and_login(client, "stats_forecast_oneoff@test.com")
    today = date.today()
    if today.month == 12:
        pytest.skip("Year rollover makes due_month ambiguous for one-off bills")

    next_month = today.month + 1
    _create_bill(
        client,
        token,
        {
            "name": "Domain",
            "amount": "250.00",
            "frequency": "one_off",
            "due_month": next_month,
            "due_day": 15,
        },
    )

    forecast = _overview(client, token)["forecast"]
    by_period = {point["period"]: _dec(point["expected_total"]) for point in forecast}
    assert by_period[f"{today.year}-{next_month:02d}"] == Decimal("250.00")
    assert sum(by_period.values()) == Decimal("250.00")


def test_forecast_only_counts_primary_currency(client):
    token = register_and_login(client, "stats_forecast_currency@test.com")

    # Two EUR templates make EUR the primary currency; the PLN bill is excluded.
    _create_bill(
        client, token, {"name": "EUR one", "currency": "EUR", "amount": "5.00"}
    )
    _create_bill(
        client, token, {"name": "EUR two", "currency": "EUR", "amount": "5.00"}
    )
    _create_bill(client, token, {"name": "PLN", "currency": "PLN", "amount": "999.00"})

    data = _overview(client, token)
    assert data["currency"] == "EUR"
    assert all(
        _dec(point["expected_total"]) == Decimal("10.00") for point in data["forecast"]
    )


# ---------------------------------------------------------------------------
# By category
# ---------------------------------------------------------------------------


def test_by_category_aggregation_and_ordering(client_db):
    client, db = client_db
    token = register_and_login(client, "stats_category@test.com")
    today = date.today()
    current = today.strftime("%Y-%m")
    previous = _shift(current, -1)

    housing = _create_bill(client, token, {"name": "Rent", "category": "housing"})
    utilities = _create_bill(client, token, {"name": "Power", "category": "utilities"})

    h_cur = _insert_instance(
        db,
        housing,
        period=current,
        due_date=today + timedelta(days=5),
        amount="300.00",
    )
    _insert_instance(
        db,
        housing,
        period=previous,
        due_date=_day_in(previous, 5),
        amount="100.00",
    )
    u_cur = _insert_instance(
        db,
        utilities,
        period=current,
        due_date=today + timedelta(days=5),
        amount="200.00",
    )

    _pay(client, token, h_cur.id, "50.00", paid_on=today.isoformat())
    _pay(client, token, u_cur.id, "150.00", paid_on=today.isoformat())

    cats = _overview(client, token)["by_category"]
    assert [c["category"]["key"] for c in cats] == ["utilities", "housing"]
    assert _dec(cats[0]["paid_total"]) == Decimal("150.00")
    assert _dec(cats[0]["due_total"]) == Decimal("200.00")
    assert _dec(cats[1]["paid_total"]) == Decimal("50.00")
    assert _dec(cats[1]["due_total"]) == Decimal("400.00")


def test_by_category_tie_break_and_zero_rows_omitted(client_db):
    client, db = client_db
    token = register_and_login(client, "stats_category_tie@test.com")
    today = date.today()
    period = today.strftime("%Y-%m")

    housing = _create_bill(client, token, {"name": "Rent", "category": "housing"})
    utilities = _create_bill(client, token, {"name": "Power", "category": "utilities"})
    other = _create_bill(client, token, {"name": "Misc", "category": "other"})

    h = _insert_instance(
        db,
        housing,
        period=period,
        due_date=today + timedelta(days=3),
        amount="100.00",
    )
    u = _insert_instance(
        db,
        utilities,
        period=period,
        due_date=today + timedelta(days=3),
        amount="100.00",
    )
    _insert_instance(
        db,
        other,
        period=period,
        due_date=today + timedelta(days=3),
        amount="0.00",
    )

    _pay(client, token, h.id, "100.00", paid_on=today.isoformat())
    _pay(client, token, u.id, "100.00", paid_on=today.isoformat())

    cats = _overview(client, token)["by_category"]
    assert [c["category"]["key"] for c in cats] == ["housing", "utilities"]


# ---------------------------------------------------------------------------
# Attention
# ---------------------------------------------------------------------------


def test_attention_selection_and_fields(client_db):
    client, db = client_db
    token = register_and_login(client, "stats_attention@test.com")
    today = date.today()
    period = today.strftime("%Y-%m")

    overdue_bill = _create_bill(client, token, {"name": "Overdue"})
    soon_bill = _create_bill(client, token, {"name": "Soon"})
    later_bill = _create_bill(client, token, {"name": "Later"})
    paid_bill = _create_bill(client, token, {"name": "Inserted paid"})
    fully_bill = _create_bill(
        client, token, {"name": "Fully paid", "frequency": "one_off"}
    )
    eur_bill = _create_bill(client, token, {"name": "EUR overdue", "currency": "EUR"})

    overdue = _insert_instance(
        db,
        overdue_bill,
        period=period,
        due_date=today - timedelta(days=2),
        amount="120.00",
        status=PaymentStatus.overdue,
    )
    soon = _insert_instance(
        db,
        soon_bill,
        period=period,
        due_date=today + timedelta(days=10),
        amount="80.00",
    )
    _insert_instance(
        db,
        later_bill,
        period=period,
        due_date=today + timedelta(days=40),
        amount="50.00",
    )
    _insert_instance(
        db,
        paid_bill,
        period=period,
        due_date=today - timedelta(days=1),
        amount="60.00",
        status=PaymentStatus.paid,
        paid_amount="60.00",
    )
    fully = _insert_instance(
        db,
        fully_bill,
        period=period,
        due_date=today - timedelta(days=1),
        amount="40.00",
    )
    _insert_instance(
        db,
        eur_bill,
        period=period,
        due_date=today - timedelta(days=1),
        amount="999.00",
        status=PaymentStatus.overdue,
    )

    _pay(client, token, soon.id, "30.00", paid_on=today.isoformat())
    _pay(client, token, fully.id, "40.00", paid_on=today.isoformat())

    data = _overview(client, token)
    assert data["currency"] == "PLN"
    assert [a["instance_id"] for a in data["attention"]] == [overdue.id, soon.id]

    first = data["attention"][0]
    assert first["bill_name"] == "Overdue"
    assert first["period"] == period
    assert first["due_date"] == (today - timedelta(days=2)).isoformat()
    assert _dec(first["amount"]) == Decimal("120.00")
    assert first["paid_amount"] is None
    assert _dec(first["remaining"]) == Decimal("120.00")
    assert first["status"] == "overdue"

    second = data["attention"][1]
    assert second["bill_name"] == "Soon"
    assert _dec(second["paid_amount"]) == Decimal("30.00")
    assert _dec(second["remaining"]) == Decimal("50.00")
    assert second["status"] == "upcoming"


def test_attention_limit_and_ordering(client_db):
    client, db = client_db
    token = register_and_login(client, "stats_attention_limit@test.com")
    today = date.today()
    period = today.strftime("%Y-%m")
    bill_id = _create_bill(client, token)

    inserted: list[tuple[date, int]] = []
    for offset in range(12):
        due = today - timedelta(days=offset)
        inst = _insert_instance(
            db,
            bill_id,
            period=_shift(period, -offset),
            due_date=due,
            amount="10.00",
            status=PaymentStatus.overdue,
        )
        inserted.append((due, inst.id))
    # Well outside the 30-day window, even though unpaid.
    _insert_instance(
        db,
        bill_id,
        period=_shift(period, -12),
        due_date=today + timedelta(days=40),
        amount="10.00",
    )

    expected = [inst_id for _, inst_id in sorted(inserted)][:10]
    data = _overview(client, token)
    assert [a["instance_id"] for a in data["attention"]] == expected


def test_attention_same_due_date_orders_by_id(client_db):
    client, db = client_db
    token = register_and_login(client, "stats_attention_tie@test.com")
    today = date.today()
    current = today.strftime("%Y-%m")
    previous = _shift(current, -1)
    due = today + timedelta(days=5)

    bill_a = _create_bill(client, token, {"name": "A"})
    bill_b = _create_bill(client, token, {"name": "B"})
    first = _insert_instance(db, bill_a, period=current, due_date=due, amount="10.00")
    second = _insert_instance(db, bill_b, period=previous, due_date=due, amount="20.00")

    data = _overview(client, token)
    assert [a["instance_id"] for a in data["attention"]] == [first.id, second.id]


# ---------------------------------------------------------------------------
# Scoping and empty state
# ---------------------------------------------------------------------------


def test_deleted_instances_excluded_everywhere(client_db):
    client, db = client_db
    token = register_and_login(client, "stats_deleted@test.com")
    today = date.today()
    period = today.strftime("%Y-%m")

    active_bill = _create_bill(client, token, {"name": "Active"})
    deleted_bill = _create_bill(client, token, {"name": "Deleted"})

    active = _insert_instance(
        db,
        active_bill,
        period=period,
        due_date=today + timedelta(days=5),
        amount="100.00",
    )
    deleted = _insert_instance(
        db,
        deleted_bill,
        period=period,
        due_date=today - timedelta(days=1),
        amount="500.00",
        status=PaymentStatus.overdue,
        is_deleted=True,
    )
    # A ledger event on a soft-deleted instance must not be counted either.
    _pay(client, token, deleted.id, "30.00", paid_on=today.isoformat())

    data = _overview(client, token)
    assert _dec(data["summary"]["due_total"]) == Decimal("100.00")
    assert _dec(data["summary"]["paid_total"]) == Decimal("0")
    assert _dec(data["summary"]["remaining_total"]) == Decimal("100.00")
    assert data["summary"]["total_count"] == 1
    assert data["summary"]["overdue_count"] == 0
    assert [a["instance_id"] for a in data["attention"]] == [active.id]
    assert all(_dec(p["paid_total"]) == Decimal("0") for p in data["trend"])
    assert len(data["by_category"]) == 1
    assert data["by_category"][0]["category"]["key"] == "utilities"
    assert _dec(data["by_category"][0]["paid_total"]) == Decimal("0")
    assert _dec(data["by_category"][0]["due_total"]) == Decimal("100.00")


def test_other_users_are_isolated(client_db):
    client, db = client_db
    token_a = register_and_login(client, "stats_isolation_a@test.com")
    token_b = register_and_login(client, "stats_isolation_b@test.com")
    today = date.today()
    period = today.strftime("%Y-%m")

    bill_a = _create_bill(client, token_a, {"name": "A bill", "currency": "PLN"})
    bill_b = _create_bill(client, token_b, {"name": "B bill", "currency": "USD"})

    _insert_instance(
        db,
        bill_a,
        period=period,
        due_date=today + timedelta(days=2),
        amount="100.00",
    )
    _insert_instance(
        db,
        bill_b,
        period=period,
        due_date=today - timedelta(days=2),
        amount="700.00",
        status=PaymentStatus.overdue,
    )

    data_b = _overview(client, token_b)
    assert data_b["currency"] == "USD"
    assert data_b["other_currencies"] == []
    assert _dec(data_b["summary"]["due_total"]) == Decimal("700.00")
    assert [a["bill_name"] for a in data_b["attention"]] == ["B bill"]

    data_a = _overview(client, token_a)
    assert data_a["currency"] == "PLN"
    assert _dec(data_a["summary"]["due_total"]) == Decimal("100.00")
    assert [a["bill_name"] for a in data_a["attention"]] == ["A bill"]


def test_empty_state_defaults_to_pln(client):
    token = register_and_login(client, "stats_empty@test.com")
    today = date.today()
    data = _overview(client, token)

    assert data["month"] == today.strftime("%Y-%m")
    assert data["months"] == 6
    assert data["currency"] == "PLN"
    assert data["other_currencies"] == []

    summary = data["summary"]
    assert _dec(summary["due_total"]) == 0
    assert _dec(summary["paid_total"]) == 0
    assert _dec(summary["remaining_total"]) == 0
    assert summary["total_count"] == 0
    assert summary["paid_count"] == 0
    assert summary["upcoming_count"] == 0
    assert summary["overdue_count"] == 0
    assert _dec(summary["overdue_total"]) == 0

    assert len(data["trend"]) == 6
    assert [p["period"] for p in data["trend"]] == [
        _shift(today.strftime("%Y-%m"), offset) for offset in range(-5, 1)
    ]
    assert all(
        _dec(p["paid_total"]) == 0 and _dec(p["due_total"]) == 0 for p in data["trend"]
    )
    assert data["by_category"] == []
    assert data["attention"] == []


# ---------------------------------------------------------------------------
# Validation and auth
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "query",
    [
        "?month=2026-9",
        "?month=notamonth",
        "?month=2026-13",
        "?month=2026-00",
        "?months=0",
        "?months=25",
        "?months=abc",
    ],
)
def test_invalid_params_return_422(client, query: str):
    token = register_and_login(client, "stats_invalid@test.com")
    r = client.get(f"/stats/overview{query}", headers=auth(token))
    assert r.status_code == 422, query


@pytest.mark.parametrize("query", ["?months=1", "?months=24", "?month=2026-01"])
def test_valid_boundary_params(client, query: str):
    token = register_and_login(client, "stats_valid@test.com")
    r = client.get(f"/stats/overview{query}", headers=auth(token))
    assert r.status_code == 200, r.text


def test_requires_authentication(client):
    r = client.get("/stats/overview")
    assert r.status_code == 401
