"""Integration tests for POST /bills/generate-instances (series generator).

Covers the eligible-template filter, the current-month+1..+months range,
idempotency via (bill_id, period), ownership errors, and period selection
per frequency.
"""

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.models.bill import PaymentInstance, PaymentStatus
from tests.conftest import auth, register_and_login

_BILL = {
    "name": "Electricity",
    "category": "utilities",
    "frequency": "monthly",
    "amount": "120.00",
    "currency": "PLN",
    "due_day": 15,
    "notes": None,
    "is_paused": False,
}


def _create_bill(client, token: str, overrides: dict | None = None) -> int:
    payload = {**_BILL, **(overrides or {})}
    r = client.post("/bills", json=payload, headers=auth(token))
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _current_month() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _shift(period: str, delta: int) -> str:
    year, month = map(int, period.split("-"))
    total = year * 12 + month - 1 + delta
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


def _generate(client, token: str, **body):
    return client.post("/bills/generate-instances", json=body, headers=auth(token))


def _periods_in_db(db, bill_id: int) -> set[str]:
    return {
        row.period
        for row in db.query(PaymentInstance.period).filter(
            PaymentInstance.bill_id == bill_id
        )
    }


# ---------------------------------------------------------------------------
# Range and response shape
# ---------------------------------------------------------------------------


def test_generate_defaults_to_six_months(client):
    token = register_and_login(client, "gen_default@test.com")
    r = _generate(client, token)
    assert r.status_code == 200, r.text
    assert r.json() == {"created": 0, "bill_count": 0, "months": 6}


def test_monthly_generates_current_plus_one_through_plus_months(client_db):
    client, db = client_db
    token = register_and_login(client, "gen_monthly@test.com")
    bill_id = _create_bill(client, token)

    r = _generate(client, token, months=6)
    assert r.status_code == 200, r.text
    assert r.json() == {"created": 6, "bill_count": 1, "months": 6}

    current = _current_month()
    assert _periods_in_db(db, bill_id) == {
        _shift(current, offset) for offset in range(1, 7)
    }


def test_generate_is_idempotent(client_db):
    client, db = client_db
    token = register_and_login(client, "gen_idempotent@test.com")
    bill_id = _create_bill(client, token)
    current = _current_month()

    first = _generate(client, token, months=3)
    assert first.status_code == 200, first.text
    assert first.json()["created"] == 3

    second = _generate(client, token, months=3)
    assert second.status_code == 200, second.text
    assert second.json() == {"created": 0, "bill_count": 1, "months": 3}
    assert _periods_in_db(db, bill_id) == {
        _shift(current, offset) for offset in (1, 2, 3)
    }


def test_generate_periods_per_frequency(client_db):
    client, db = client_db
    token = register_and_login(client, "gen_frequency@test.com")
    current = _current_month()

    monthly = _create_bill(client, token, {"name": "Monthly"})
    every2 = _create_bill(
        client, token, {"name": "Every 2", "frequency": "every_2_months"}
    )
    quarterly = _create_bill(
        client, token, {"name": "Quarterly", "frequency": "quarterly"}
    )
    annual = _create_bill(client, token, {"name": "Annual", "frequency": "annual"})

    r = _generate(client, token, months=12)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["months"] == 12
    assert data["bill_count"] == 4

    assert _periods_in_db(db, monthly) == {
        _shift(current, offset) for offset in range(1, 13)
    }
    assert _periods_in_db(db, every2) == {
        _shift(current, offset) for offset in range(2, 13, 2)
    }
    assert _periods_in_db(db, quarterly) == {
        _shift(current, offset) for offset in range(3, 13, 3)
    }
    # Annual anchored at the current month → only +12 falls in range.
    assert _periods_in_db(db, annual) == {_shift(current, 12)}
    assert data["created"] == 12 + 6 + 4 + 1


def test_soft_deleted_instance_acts_as_tombstone(client_db):
    client, db = client_db
    token = register_and_login(client, "gen_tombstone@test.com")
    bill_id = _create_bill(client, token)
    target = _shift(_current_month(), 1)
    db.add(
        PaymentInstance(
            bill_id=bill_id,
            period=target,
            due_date=date(int(target[:4]), int(target[5:]), 15),
            amount=Decimal("120.00"),
            status=PaymentStatus.upcoming,
            is_deleted=True,
        )
    )
    db.commit()

    r = _generate(client, token, months=1)
    assert r.status_code == 200, r.text
    assert r.json()["created"] == 0
    assert _periods_in_db(db, bill_id) == {target}


# ---------------------------------------------------------------------------
# Eligibility and ownership
# ---------------------------------------------------------------------------


def test_paused_archived_and_one_off_are_skipped(client_db):
    client, db = client_db
    token = register_and_login(client, "gen_skipped@test.com")

    paused = _create_bill(client, token, {"name": "Paused", "is_paused": True})
    archived = _create_bill(client, token, {"name": "Archived"})
    r = client.post(f"/bills/{archived}/archive", headers=auth(token))
    assert r.status_code == 204, r.text
    one_off = _create_bill(client, token, {"name": "One-off", "frequency": "one_off"})

    r = _generate(client, token, months=6)
    assert r.status_code == 200, r.text
    assert r.json() == {"created": 0, "bill_count": 0, "months": 6}
    for bill_id in (paused, archived, one_off):
        assert _periods_in_db(db, bill_id) == set()


def test_bill_ids_limits_generation_to_selected_bills(client_db):
    client, db = client_db
    token = register_and_login(client, "gen_subset@test.com")

    selected = _create_bill(client, token, {"name": "Selected"})
    other = _create_bill(client, token, {"name": "Other"})

    r = _generate(client, token, months=2, bill_ids=[selected])
    assert r.status_code == 200, r.text
    assert r.json() == {"created": 2, "bill_count": 1, "months": 2}

    current = _current_month()
    assert _periods_in_db(db, selected) == {
        _shift(current, 1),
        _shift(current, 2),
    }
    assert _periods_in_db(db, other) == set()


def test_foreign_or_unknown_bill_id_returns_404(client_db):
    client, db = client_db
    token_a = register_and_login(client, "gen_owner_a@test.com")
    token_b = register_and_login(client, "gen_owner_b@test.com")
    foreign = _create_bill(client, token_b, {"name": "B's bill"})

    r = _generate(client, token_a, bill_ids=[foreign])
    assert r.status_code == 404

    r = _generate(client, token_a, bill_ids=[999999])
    assert r.status_code == 404

    # A valid id mixed with a foreign one still fails before creating anything.
    own = _create_bill(client, token_a, {"name": "A's bill"})
    r = _generate(client, token_a, bill_ids=[own, foreign])
    assert r.status_code == 404
    assert _periods_in_db(db, own) == set()


# ---------------------------------------------------------------------------
# Validation and auth
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("months", [0, 25, -1, "abc"])
def test_invalid_months_returns_422(client, months):
    token = register_and_login(client, "gen_bounds@test.com")
    r = _generate(client, token, months=months)
    assert r.status_code == 422, months


@pytest.mark.parametrize("months", [1, 24])
def test_boundary_months_are_valid(client, months):
    token = register_and_login(client, "gen_bounds_ok@test.com")
    r = _generate(client, token, months=months)
    assert r.status_code == 200, r.text
    assert r.json()["months"] == months


def test_requires_authentication(client):
    r = client.post("/bills/generate-instances", json={"months": 6})
    assert r.status_code == 401
