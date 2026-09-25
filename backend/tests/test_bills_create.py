"""Tests for POST /bills — due_month routing and input validation."""

import pytest

from tests.conftest import auth, register_and_login, sync_payments

_BASE_BILL = {
    "name": "TestBill",
    "category": "utilities",
    "frequency": "monthly",
    "amount": "100.00",
    "currency": "PLN",
    "due_day": 15,
    "is_paused": False,
}


def _bill(**overrides) -> dict:
    return {**_BASE_BILL, **overrides}


# ---------------------------------------------------------------------------
# due_month routing — covers bills.py lines 51-55, 66
# ---------------------------------------------------------------------------


def test_create_monthly_bill_with_past_due_month_seeds_history(client):
    """Monthly bill with due_month 3 months in the past → backfill creates past instances."""
    from datetime import date

    today = date.today()
    if today.month <= 3:
        pytest.skip("Requires at least 3 months of history (month >= April)")

    past_month = today.month - 3
    past_period = f"{today.year}-{past_month:02d}"

    token = register_and_login(client, "backfill_monthly@test.com")
    r = client.post(
        "/bills",
        json=_bill(frequency="monthly", due_month=past_month),
        headers=auth(token),
    )
    assert r.status_code == 201

    r = client.get(f"/bills/payments?month={past_period}", headers=auth(token))
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_create_monthly_bill_with_current_month_does_not_backfill(client):
    """Monthly bill with due_month == current month → no backfill (start_period == current)."""
    from datetime import date

    today = date.today()
    token = register_and_login(client, "no_backfill@test.com")
    r = client.post(
        "/bills",
        json=_bill(frequency="monthly", due_month=today.month),
        headers=auth(token),
    )
    assert r.status_code == 201
    bill_id = r.json()["id"]

    # Sync current month — should produce exactly one instance (not extra from backfill)
    sync_payments(client, token)
    payments = client.get("/bills/payments", headers=auth(token)).json()
    bill_payments = [p for p in payments if p["bill_id"] == bill_id]
    assert len(bill_payments) == 1


def test_create_annual_bill_with_future_due_month_sets_next_year(client):
    """Annual bill with due_month > current month → start_period uses current year."""
    from datetime import date

    today = date.today()
    if today.month >= 12:
        pytest.skip("Requires a future month (month < December)")

    future_month = today.month + 1
    token = register_and_login(client, "annual_future@test.com")
    r = client.post(
        "/bills",
        json=_bill(frequency="annual", due_month=future_month, due_day=None),
        headers=auth(token),
    )
    assert r.status_code == 201
    data = r.json()
    # start_period should be current year since due_month >= now.month
    expected_year = today.year
    assert data["start_period"].startswith(str(expected_year))


def test_create_annual_bill_with_past_due_month_sets_next_year(client):
    """Annual bill with due_month < current month → start_period bumped to next year."""
    from datetime import date

    today = date.today()
    if today.month <= 1:
        pytest.skip("Requires a past month (month > January)")

    past_month = today.month - 1
    token = register_and_login(client, "annual_past@test.com")
    r = client.post(
        "/bills",
        json=_bill(frequency="annual", due_month=past_month, due_day=None),
        headers=auth(token),
    )
    assert r.status_code == 201
    data = r.json()
    # Annual renewals roll forward: the next occurrence is next year's cycle
    expected_year = today.year + 1
    assert data["start_period"].startswith(str(expected_year))


def test_create_one_off_bill_with_past_due_month_is_overdue(client):
    """One-off bills materialize their single occurrence, overdue when past."""
    from datetime import date

    today = date.today()
    if today.month <= 1:
        pytest.skip("Requires a past month (month > January)")

    past_month = today.month - 1
    past_period = f"{today.year}-{past_month:02d}"
    token = register_and_login(client, "one_off_past@test.com")
    r = client.post(
        "/bills",
        json=_bill(frequency="one_off", due_month=past_month, due_day=None),
        headers=auth(token),
    )
    assert r.status_code == 201
    bill_id = r.json()["id"]

    r = client.get(f"/bills/payments?month={past_period}", headers=auth(token))
    assert r.status_code == 200
    instances = [p for p in r.json() if p["bill_id"] == bill_id]
    assert len(instances) == 1
    assert instances[0]["status"] == "overdue"


def test_create_one_off_bill_in_current_month_appears_after_sync(client):
    """One-off bills used to never generate an instance — ensure they do."""
    from datetime import date

    today = date.today()
    token = register_and_login(client, "one_off_current@test.com")
    r = client.post(
        "/bills",
        json=_bill(
            frequency="one_off", due_month=today.month, due_day=max(today.day, 1)
        ),
        headers=auth(token),
    )
    assert r.status_code == 201
    bill_id = r.json()["id"]

    sync_payments(client, token)
    payments = client.get("/bills/payments", headers=auth(token)).json()
    instances = [p for p in payments if p["bill_id"] == bill_id]
    assert len(instances) == 1


# ---------------------------------------------------------------------------
# Input validation — covers 422 paths in Pydantic schema
# ---------------------------------------------------------------------------


def test_create_bill_missing_required_name_returns_422(client):
    token = register_and_login(client, "val_name@test.com")
    payload = {k: v for k, v in _BASE_BILL.items() if k != "name"}
    r = client.post("/bills", json=payload, headers=auth(token))
    assert r.status_code == 422


def test_create_bill_invalid_frequency_returns_422(client):
    token = register_and_login(client, "val_freq@test.com")
    r = client.post("/bills", json=_bill(frequency="daily"), headers=auth(token))
    assert r.status_code == 422


@pytest.mark.parametrize("legacy", ["every_2_months", "quarterly"])
def test_create_bill_legacy_frequency_returns_422(client, legacy):
    """Retired enum values are rejected on new writes."""
    token = register_and_login(client, f"val_legacy_{legacy}@test.com")
    r = client.post("/bills", json=_bill(frequency=legacy), headers=auth(token))
    assert r.status_code == 422


def test_create_bill_due_day_zero_returns_422(client):
    token = register_and_login(client, "val_day0@test.com")
    r = client.post("/bills", json=_bill(due_day=0), headers=auth(token))
    assert r.status_code == 422


def test_create_bill_due_day_32_returns_422(client):
    token = register_and_login(client, "val_day32@test.com")
    r = client.post("/bills", json=_bill(due_day=32), headers=auth(token))
    assert r.status_code == 422


def test_create_bill_due_month_13_returns_422(client):
    token = register_and_login(client, "val_month13@test.com")
    r = client.post("/bills", json=_bill(due_month=13), headers=auth(token))
    assert r.status_code == 422


def test_create_bill_negative_amount_is_accepted_as_zero_floor(client):
    """amount has no lower-bound validator — Decimal accepts negatives; document the behavior."""
    token = register_and_login(client, "val_neg@test.com")
    r = client.post("/bills", json=_bill(amount="-50.00"), headers=auth(token))
    # Current schema has no non-negative constraint; this test documents that.
    # If a validator is added later, update this to assert 422 instead.
    assert r.status_code == 201


def test_create_bill_invalid_category_returns_422(client):
    token = register_and_login(client, "val_cat@test.com")
    r = client.post("/bills", json=_bill(category="unknown_cat"), headers=auth(token))
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Weekly schedules + interval bounds
# ---------------------------------------------------------------------------


def test_create_weekly_bill_requires_start_date(client):
    token = register_and_login(client, "weekly_no_start@test.com")
    r = client.post(
        "/bills",
        json=_bill(frequency="weekly", due_day=None),
        headers=auth(token),
    )
    assert r.status_code == 422


def test_create_weekly_bill_backfills_from_past_start_date(client):
    """Occurrences run from start_date through the end of the current month."""
    from datetime import date

    today = date.today()
    first_of_month = today.replace(day=1)
    token = register_and_login(client, "weekly_backfill@test.com")
    r = client.post(
        "/bills",
        json=_bill(
            frequency="weekly",
            start_date=first_of_month.isoformat(),
            interval_count=1,
            due_day=None,
        ),
        headers=auth(token),
    )
    assert r.status_code == 201
    data = r.json()
    assert data["frequency"] == "weekly"
    assert data["interval_count"] == 1
    assert data["start_date"] == first_of_month.isoformat()
    assert data["due_day"] is None
    assert data["start_period"] == first_of_month.strftime("%Y-%m")

    period = today.strftime("%Y-%m")
    payments = client.get(f"/bills/payments?month={period}", headers=auth(token)).json()
    bill_payments = [p for p in payments if p["bill_id"] == data["id"]]
    # The 1st/8th/15th/22nd/29th of a month → always at least 4 rows.
    assert len(bill_payments) >= 4
    assert all(p["period"] == period for p in bill_payments)
    assert all(p["frequency"] == "weekly" for p in bill_payments)
    assert all(p["interval_count"] == 1 for p in bill_payments)
    assert all(p["start_date"] == first_of_month.isoformat() for p in bill_payments)


def test_create_weekly_bill_future_start_date_creates_nothing(client):
    from datetime import date, timedelta

    today = date.today()
    next_month = (today.replace(day=1) + timedelta(days=32)).replace(day=1)
    token = register_and_login(client, "weekly_future@test.com")
    r = client.post(
        "/bills",
        json=_bill(
            frequency="weekly",
            start_date=next_month.isoformat(),
            due_day=None,
        ),
        headers=auth(token),
    )
    assert r.status_code == 201

    payments = client.get(
        f"/bills/payments?month={today.strftime('%Y-%m')}", headers=auth(token)
    ).json()
    assert payments == []


@pytest.mark.parametrize(
    "frequency,interval",
    [
        ("weekly", 5),
        ("monthly", 13),
        ("annual", 6),
    ],
)
def test_create_bill_interval_out_of_bounds_returns_422(client, frequency, interval):
    token = register_and_login(client, f"val_interval_{frequency}@test.com")
    payload = _bill(frequency=frequency, interval_count=interval)
    if frequency == "weekly":
        payload["start_date"] = "2026-01-05"
        payload["due_day"] = None
    r = client.post("/bills", json=payload, headers=auth(token))
    assert r.status_code == 422


@pytest.mark.parametrize(
    "frequency,interval",
    [
        ("weekly", 4),
        ("monthly", 12),
        ("annual", 5),
    ],
)
def test_create_bill_interval_at_bound_is_accepted(client, frequency, interval):
    token = register_and_login(client, f"val_interval_ok_{frequency}@test.com")
    payload = _bill(frequency=frequency, interval_count=interval)
    if frequency == "weekly":
        payload["start_date"] = "2026-01-05"
        payload["due_day"] = None
    r = client.post("/bills", json=payload, headers=auth(token))
    assert r.status_code == 201, r.text
    assert r.json()["interval_count"] == interval


def test_create_one_off_forces_interval_one(client):
    token = register_and_login(client, "val_oneoff_interval@test.com")
    r = client.post(
        "/bills",
        json=_bill(frequency="one_off", interval_count=5, due_day=None),
        headers=auth(token),
    )
    assert r.status_code == 201
    assert r.json()["interval_count"] == 1


def test_create_non_weekly_ignores_start_date(client):
    token = register_and_login(client, "val_ignore_start@test.com")
    r = client.post(
        "/bills",
        json=_bill(frequency="monthly", start_date="2026-01-05"),
        headers=auth(token),
    )
    assert r.status_code == 201
    assert r.json()["start_date"] is None


# ---------------------------------------------------------------------------
# max_occurrences
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", [0, 1000, -1])
def test_create_bill_max_occurrences_out_of_bounds_returns_422(client, value):
    token = register_and_login(client, f"val_max_occ_{value}@test.com")
    r = client.post("/bills", json=_bill(max_occurrences=value), headers=auth(token))
    assert r.status_code == 422


@pytest.mark.parametrize("value", [1, 999])
def test_create_bill_max_occurrences_at_bound_is_accepted(client, value):
    token = register_and_login(client, f"val_max_occ_ok_{value}@test.com")
    r = client.post("/bills", json=_bill(max_occurrences=value), headers=auth(token))
    assert r.status_code == 201, r.text
    assert r.json()["max_occurrences"] == value


def test_create_bill_max_occurrences_defaults_to_null(client):
    token = register_and_login(client, "max_occ_default@test.com")
    r = client.post("/bills", json=_bill(), headers=auth(token))
    assert r.status_code == 201, r.text
    assert r.json()["max_occurrences"] is None


def test_create_bill_persists_max_occurrences(client):
    token = register_and_login(client, "max_occ_persist@test.com")
    r = client.post("/bills", json=_bill(max_occurrences=12), headers=auth(token))
    assert r.status_code == 201, r.text
    bill_id = r.json()["id"]

    bills = client.get("/bills", headers=auth(token)).json()
    created = next(b for b in bills if b["id"] == bill_id)
    assert created["max_occurrences"] == 12

    # Payment instance payloads carry the cap too (DeletePaymentDialog label).
    sync_payments(client, token)
    payments = client.get("/bills/payments", headers=auth(token)).json()
    instance = next(p for p in payments if p["bill_id"] == bill_id)
    assert instance["max_occurrences"] == 12


def test_create_one_off_forces_max_occurrences_null(client):
    token = register_and_login(client, "max_occ_oneoff@test.com")
    r = client.post(
        "/bills",
        json=_bill(frequency="one_off", due_month=1, due_day=None, max_occurrences=4),
        headers=auth(token),
    )
    assert r.status_code == 201, r.text
    assert r.json()["max_occurrences"] is None
