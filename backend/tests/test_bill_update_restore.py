"""Tests for GET /bills/{id}/has-deleted-future and PATCH recreate_deleted_future."""

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.models.bill import PaymentInstance, PaymentStatus
from app.services.recurrence import _due_date_for_period
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


def _create_bill(client: TestClient, token: str, overrides: dict | None = None) -> int:
    payload = {**_BILL, **(overrides or {})}
    r = client.post("/bills", json=payload, headers=auth(token))
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _insert_instance(
    db,
    bill_id: int,
    period: str,
    due_date: date,
    status=PaymentStatus.upcoming,
    is_deleted: bool = False,
    amount="120.00",
) -> PaymentInstance:
    inst = PaymentInstance(
        bill_id=bill_id,
        period=period,
        due_date=due_date,
        amount=amount,
        status=status,
        is_deleted=is_deleted,
    )
    db.add(inst)
    db.commit()
    db.refresh(inst)
    return inst


def _current_period() -> str:
    return date.today().strftime("%Y-%m")


def _future_period() -> str:
    """One month ahead of today."""
    today = date.today()
    month = today.month % 12 + 1
    year = today.year + (1 if today.month == 12 else 0)
    return f"{year}-{month:02d}"


def _past_period() -> str:
    """One month before today."""
    today = date.today()
    month = today.month - 1 or 12
    year = today.year - (1 if today.month == 1 else 0)
    return f"{year}-{month:02d}"


# ---------------------------------------------------------------------------
# GET /bills/{id}/has-deleted-future
# ---------------------------------------------------------------------------


def test_has_deleted_future_no_instances(client_db):
    """Bill with no instances at all returns false."""
    client, db = client_db
    token = register_and_login(client, "u1@test.com")
    bill_id = _create_bill(client, token)

    r = client.get(f"/bills/{bill_id}/has-deleted-future", headers=auth(token))
    assert r.status_code == 200
    assert r.json() == {"has_deleted_future": False}


def test_has_deleted_future_with_current_period_tombstone(client_db):
    """Tombstone in current period returns true."""
    client, db = client_db
    token = register_and_login(client, "u2@test.com")
    bill_id = _create_bill(client, token)
    period = _current_period()
    _insert_instance(db, bill_id, period, date.today(), is_deleted=True)

    r = client.get(f"/bills/{bill_id}/has-deleted-future", headers=auth(token))
    assert r.status_code == 200
    assert r.json() == {"has_deleted_future": True}


def test_has_deleted_future_only_past_tombstone_returns_false(client_db):
    """Tombstone in a past period does not count — returns false."""
    client, db = client_db
    token = register_and_login(client, "u3@test.com")
    bill_id = _create_bill(client, token)
    past = _past_period()
    year, month = map(int, past.split("-"))
    _insert_instance(db, bill_id, past, date(year, month, 15), is_deleted=True)

    r = client.get(f"/bills/{bill_id}/has-deleted-future", headers=auth(token))
    assert r.status_code == 200
    assert r.json() == {"has_deleted_future": False}


def test_has_deleted_future_cross_user_returns_404(client_db):
    """Another user cannot probe a bill they don't own."""
    client, db = client_db
    tok_a = register_and_login(client, "a1@test.com")
    tok_b = register_and_login(client, "b1@test.com")
    bill_id = _create_bill(client, tok_a)

    r = client.get(f"/bills/{bill_id}/has-deleted-future", headers=auth(tok_b))
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /bills/{id} with recreate_deleted_future=true
# ---------------------------------------------------------------------------


def test_patch_restore_flips_tombstone_to_active(client_db):
    """recreate_deleted_future=true restores is_deleted=False and status=upcoming."""
    client, db = client_db
    token = register_and_login(client, "u4@test.com")
    bill_id = _create_bill(client, token)
    period = _current_period()
    inst = _insert_instance(db, bill_id, period, date.today(), is_deleted=True)

    r = client.patch(
        f"/bills/{bill_id}",
        json={"recreate_deleted_future": True},
        headers=auth(token),
    )
    assert r.status_code == 200

    db.expire_all()
    refreshed = db.get(PaymentInstance, inst.id)
    assert refreshed.is_deleted is False
    assert refreshed.status == PaymentStatus.upcoming


def test_patch_restore_updates_amount(client_db):
    """Restored instances pick up the template's updated amount."""
    client, db = client_db
    token = register_and_login(client, "u5@test.com")
    bill_id = _create_bill(client, token)
    period = _current_period()
    inst = _insert_instance(
        db, bill_id, period, date.today(), is_deleted=True, amount="120.00"
    )

    r = client.patch(
        f"/bills/{bill_id}",
        json={"amount": "250.00", "recreate_deleted_future": True},
        headers=auth(token),
    )
    assert r.status_code == 200

    db.expire_all()
    refreshed = db.get(PaymentInstance, inst.id)
    assert float(refreshed.amount) == pytest.approx(250.00)


def test_patch_restore_recalculates_due_date(client_db):
    """Restored instances get due_date recalculated from the updated due_day."""
    client, db = client_db
    token = register_and_login(client, "u6@test.com")
    bill_id = _create_bill(client, token)  # due_day=15
    period = _current_period()
    year, month = map(int, period.split("-"))
    inst = _insert_instance(db, bill_id, period, date(year, month, 15), is_deleted=True)

    r = client.patch(
        f"/bills/{bill_id}",
        json={"due_day": 20, "recreate_deleted_future": True},
        headers=auth(token),
    )
    assert r.status_code == 200

    db.expire_all()
    refreshed = db.get(PaymentInstance, inst.id)
    assert refreshed.due_date == _due_date_for_period(period, 20)


def test_patch_without_restore_flag_leaves_tombstone_intact(client_db):
    """Default PATCH (recreate_deleted_future omitted) does not touch tombstones."""
    client, db = client_db
    token = register_and_login(client, "u7@test.com")
    bill_id = _create_bill(client, token)
    period = _current_period()
    inst = _insert_instance(db, bill_id, period, date.today(), is_deleted=True)

    r = client.patch(
        f"/bills/{bill_id}",
        json={"amount": "200.00"},
        headers=auth(token),
    )
    assert r.status_code == 200

    db.expire_all()
    assert db.get(PaymentInstance, inst.id).is_deleted is True


def test_patch_restore_no_tombstones_is_noop(client_db):
    """recreate_deleted_future=true with no tombstones: 200, template updated, no error."""
    client, db = client_db
    token = register_and_login(client, "u8@test.com")
    bill_id = _create_bill(client, token)
    # active instance (not deleted)
    period = _current_period()
    _insert_instance(db, bill_id, period, date.today(), is_deleted=False)

    r = client.patch(
        f"/bills/{bill_id}",
        json={"amount": "300.00", "recreate_deleted_future": True},
        headers=auth(token),
    )
    assert r.status_code == 200
    assert float(r.json()["amount"]) == pytest.approx(300.00)


def test_patch_restore_does_not_restore_past_tombstones(client_db):
    """Past-period tombstones are ignored; only current/future ones are restored."""
    client, db = client_db
    token = register_and_login(client, "u9@test.com")
    bill_id = _create_bill(client, token)

    past = _past_period()
    past_year, past_month = map(int, past.split("-"))
    past_inst = _insert_instance(
        db, bill_id, past, date(past_year, past_month, 15), is_deleted=True
    )

    future = _future_period()
    future_year, future_month = map(int, future.split("-"))
    future_inst = _insert_instance(
        db, bill_id, future, date(future_year, future_month, 15), is_deleted=True
    )

    r = client.patch(
        f"/bills/{bill_id}",
        json={"recreate_deleted_future": True},
        headers=auth(token),
    )
    assert r.status_code == 200

    db.expire_all()
    assert db.get(PaymentInstance, past_inst.id).is_deleted is True  # untouched
    assert db.get(PaymentInstance, future_inst.id).is_deleted is False  # restored


def test_patch_restore_cross_user_returns_403(client_db):
    """Cross-user PATCH with restore flag is blocked."""
    client, db = client_db
    tok_a = register_and_login(client, "a2@test.com")
    tok_b = register_and_login(client, "b2@test.com")
    bill_id = _create_bill(client, tok_a)

    r = client.patch(
        f"/bills/{bill_id}",
        json={"recreate_deleted_future": True},
        headers=auth(tok_b),
    )
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# PATCH /bills/{id} — weekly schedule changes and interval validation
# ---------------------------------------------------------------------------


def test_patch_weekly_schedule_change_respaces_future_unpaid(client_db):
    """Changing a weekly interval re-spaces future unpaid instances from the
    first occurrence on/after today. Paid and soft-deleted rows are untouched."""
    client, db = client_db
    token = register_and_login(client, "weekly_patch@test.com")
    today = date.today()
    # Future anchor so create does not backfill the current month.
    start = today + timedelta(days=30)
    bill_id = _create_bill(
        client,
        token,
        {
            "frequency": "weekly",
            "start_date": start.isoformat(),
            "interval_count": 1,
            "due_day": None,
        },
    )

    first = _insert_instance(
        db,
        bill_id,
        (today + timedelta(days=40)).strftime("%Y-%m"),
        today + timedelta(days=40),
    )
    second = _insert_instance(
        db,
        bill_id,
        (today + timedelta(days=50)).strftime("%Y-%m"),
        today + timedelta(days=50),
    )
    third = _insert_instance(
        db,
        bill_id,
        (today + timedelta(days=60)).strftime("%Y-%m"),
        today + timedelta(days=60),
    )
    paid = _insert_instance(
        db,
        bill_id,
        (today + timedelta(days=45)).strftime("%Y-%m"),
        today + timedelta(days=45),
        status=PaymentStatus.paid,
    )
    deleted = _insert_instance(
        db,
        bill_id,
        (today + timedelta(days=55)).strftime("%Y-%m"),
        today + timedelta(days=55),
        is_deleted=True,
    )

    r = client.patch(
        f"/bills/{bill_id}", json={"interval_count": 2}, headers=auth(token)
    )
    assert r.status_code == 200, r.text
    assert r.json()["interval_count"] == 2

    db.expire_all()
    assert db.get(PaymentInstance, first.id).due_date == start
    assert db.get(PaymentInstance, second.id).due_date == start + timedelta(days=14)
    assert db.get(PaymentInstance, third.id).due_date == start + timedelta(days=28)
    assert db.get(PaymentInstance, first.id).period == start.strftime("%Y-%m")
    # Paid and soft-deleted rows keep their old dates.
    assert db.get(PaymentInstance, paid.id).due_date == today + timedelta(days=45)
    assert db.get(PaymentInstance, deleted.id).due_date == today + timedelta(days=55)


def test_patch_weekly_to_monthly_clears_start_date_and_due_day(client_db):
    client, db = client_db
    token = register_and_login(client, "weekly_to_monthly@test.com")
    start = date.today() + timedelta(days=10)
    bill_id = _create_bill(
        client,
        token,
        {
            "frequency": "weekly",
            "start_date": start.isoformat(),
            "due_day": None,
        },
    )

    r = client.patch(
        f"/bills/{bill_id}",
        json={"frequency": "monthly", "due_day": 10},
        headers=auth(token),
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["frequency"] == "monthly"
    assert data["start_date"] is None
    assert data["due_day"] == 10
    assert data["interval_count"] == 1


def test_patch_monthly_to_weekly_requires_start_date(client_db):
    client, db = client_db
    token = register_and_login(client, "monthly_to_weekly@test.com")
    bill_id = _create_bill(client, token)  # monthly, no start_date

    r = client.patch(
        f"/bills/{bill_id}", json={"frequency": "weekly"}, headers=auth(token)
    )
    assert r.status_code == 422


def test_patch_interval_out_of_bounds_returns_422(client_db):
    client, db = client_db
    token = register_and_login(client, "patch_interval_bounds@test.com")
    bill_id = _create_bill(client, token)  # monthly → max 12

    r = client.patch(
        f"/bills/{bill_id}", json={"interval_count": 13}, headers=auth(token)
    )
    assert r.status_code == 422
