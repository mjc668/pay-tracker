"""Integration tests for the payment ledger endpoints.

Covers POST /bills/payments/{id}/payments, DELETE
/bills/payments/{id}/payments/{payment_id}, the reimplemented legacy /pay
and /unpay flows, validation, scoping, and the `payments` response field.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from tests.conftest import auth, register_and_login, sync_payments

_BILL = {
    "name": "Electricity",
    "category": "utilities",
    "frequency": "monthly",
    "amount": 120.00,
    "currency": "PLN",
    "due_day": 15,
    "notes": None,
    "is_paused": False,
}

_PARTIAL_STATUSES = ("upcoming", "overdue")


def _create_bill(client, token: str, overrides: dict | None = None) -> int:
    payload = {**_BILL, **(overrides or {})}
    r = client.post("/bills", json=payload, headers=auth(token))
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _seed_instance(client, token: str, bill_id: int) -> dict:
    sync_payments(client, token)
    r = client.get("/bills/payments", headers=auth(token))
    assert r.status_code == 200, r.text
    instances = [i for i in r.json() if i["bill_id"] == bill_id]
    assert instances, f"No payment instance found for bill_id={bill_id}"
    return instances[0]


def _instances_for_bill_in_month(
    client, token: str, bill_id: int, month: str
) -> list[dict]:
    r = client.get(f"/bills/payments?month={month}", headers=auth(token))
    assert r.status_code == 200, r.text
    return [i for i in r.json() if i["bill_id"] == bill_id]


def _next_period(period: str) -> str:
    year, month = int(period[:4]), int(period[5:7])
    month += 1
    if month > 12:
        month = 1
        year += 1
    return f"{year:04d}-{month:02d}"


def _add_payment(
    client,
    token: str,
    instance_id: int,
    amount,
    *,
    paid_on: str | None = None,
    note: str | None = None,
):
    return client.post(
        f"/bills/payments/{instance_id}/payments",
        json={"amount": amount, "paid_on": paid_on, "note": note},
        headers=auth(token),
    )


def _delete_event(client, token: str, instance_id: int, payment_id: int):
    return client.delete(
        f"/bills/payments/{instance_id}/payments/{payment_id}",
        headers=auth(token),
    )


def _legacy_pay(
    client,
    token: str,
    instance_id: int,
    *,
    paid_amount=None,
    notes: str | None = None,
):
    return client.post(
        f"/bills/payments/{instance_id}/pay",
        json={"paid_amount": paid_amount, "notes": notes},
        headers=auth(token),
    )


# ---------------------------------------------------------------------------
# Recording payments
# ---------------------------------------------------------------------------


def test_full_payment_marks_paid_and_generates_next_instance(client):
    tok = register_and_login(client, "ledger_full@test.com")
    bill_id = _create_bill(client, tok)
    inst = _seed_instance(client, tok, bill_id)

    r = _add_payment(client, tok, inst["id"], "120.00", note="full payment")
    assert r.status_code == 200, r.text
    data = r.json()

    assert data["status"] == "paid"
    assert Decimal(str(data["paid_amount"])) == Decimal("120.00")
    assert data["paid_at"] is not None
    assert len(data["payments"]) == 1
    payment = data["payments"][0]
    assert payment["instance_id"] == inst["id"]
    assert Decimal(str(payment["amount"])) == Decimal("120.00")
    assert payment["paid_on"] == date.today().isoformat()
    assert payment["note"] == "full payment"
    assert payment["created_at"]

    next_month = _next_period(inst["period"])
    assert len(_instances_for_bill_in_month(client, tok, bill_id, next_month)) == 1


def test_partial_then_completing_payment(client):
    tok = register_and_login(client, "ledger_partial@test.com")
    bill_id = _create_bill(client, tok)
    inst = _seed_instance(client, tok, bill_id)
    next_month = _next_period(inst["period"])

    r1 = _add_payment(client, tok, inst["id"], "50.00", note="part 1")
    assert r1.status_code == 200, r1.text
    d1 = r1.json()
    assert d1["status"] in _PARTIAL_STATUSES
    assert d1["status"] != "paid"
    assert Decimal(str(d1["paid_amount"])) == Decimal("50.00")
    assert d1["paid_at"] is None
    assert len(d1["payments"]) == 1
    # Not fully paid yet: no next recurring instance.
    assert _instances_for_bill_in_month(client, tok, bill_id, next_month) == []

    r2 = _add_payment(client, tok, inst["id"], "70.00", note="part 2")
    assert r2.status_code == 200, r2.text
    d2 = r2.json()
    assert d2["status"] == "paid"
    assert Decimal(str(d2["paid_amount"])) == Decimal("120.00")
    assert d2["paid_at"] is not None
    assert [p["note"] for p in d2["payments"]] == ["part 1", "part 2"]
    assert [Decimal(str(p["amount"])) for p in d2["payments"]] == [
        Decimal("50.00"),
        Decimal("70.00"),
    ]
    # Fully paid: next instance generated exactly once.
    assert len(_instances_for_bill_in_month(client, tok, bill_id, next_month)) == 1


def test_overpayment_keeps_paid_and_reports_total(client):
    tok = register_and_login(client, "ledger_over@test.com")
    bill_id = _create_bill(client, tok)
    inst = _seed_instance(client, tok, bill_id)

    r1 = _add_payment(client, tok, inst["id"], "120.00")
    assert r1.status_code == 200, r1.text
    r2 = _add_payment(client, tok, inst["id"], "10.00", note="extra")
    assert r2.status_code == 200, r2.text

    data = r2.json()
    assert data["status"] == "paid"
    assert Decimal(str(data["paid_amount"])) == Decimal("130.00")
    assert len(data["payments"]) == 2


def test_explicit_past_paid_on_is_recorded(client):
    tok = register_and_login(client, "ledger_past@test.com")
    bill_id = _create_bill(client, tok)
    inst = _seed_instance(client, tok, bill_id)

    past = (date.today() - timedelta(days=3)).isoformat()
    r = _add_payment(client, tok, inst["id"], "10.00", paid_on=past)
    assert r.status_code == 200, r.text
    assert r.json()["payments"][0]["paid_on"] == past


def test_list_payments_includes_ledger_rows(client):
    tok = register_and_login(client, "ledger_list@test.com")
    bill_id = _create_bill(client, tok)
    inst = _seed_instance(client, tok, bill_id)

    r = _add_payment(client, tok, inst["id"], "60.00", note="half")
    assert r.status_code == 200, r.text

    listed = [
        i
        for i in _instances_for_bill_in_month(client, tok, bill_id, inst["period"])
        if i["id"] == inst["id"]
    ]
    assert len(listed) == 1
    assert len(listed[0]["payments"]) == 1
    assert listed[0]["payments"][0]["note"] == "half"


def test_paused_template_does_not_generate_next_instance(client):
    tok = register_and_login(client, "ledger_paused@test.com")
    bill_id = _create_bill(client, tok)
    inst = _seed_instance(client, tok, bill_id)
    next_month = _next_period(inst["period"])

    r = client.patch(f"/bills/{bill_id}", json={"is_paused": True}, headers=auth(tok))
    assert r.status_code == 200, r.text

    r = _add_payment(client, tok, inst["id"], "120.00")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "paid"
    assert _instances_for_bill_in_month(client, tok, bill_id, next_month) == []


# ---------------------------------------------------------------------------
# Deleting events
# ---------------------------------------------------------------------------


def test_delete_event_recomputes_then_clears(client):
    tok = register_and_login(client, "ledger_del@test.com")
    bill_id = _create_bill(client, tok)
    inst = _seed_instance(client, tok, bill_id)

    _add_payment(client, tok, inst["id"], "50.00", note="part 1")
    r2 = _add_payment(client, tok, inst["id"], "70.00", note="part 2")
    assert r2.status_code == 200, r2.text
    second_id = r2.json()["payments"][1]["id"]

    r = _delete_event(client, tok, inst["id"], second_id)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] in _PARTIAL_STATUSES
    assert data["status"] != "paid"
    assert Decimal(str(data["paid_amount"])) == Decimal("50.00")
    assert data["paid_at"] is None
    assert len(data["payments"]) == 1
    assert data["payments"][0]["note"] == "part 1"

    remaining_id = data["payments"][0]["id"]
    r = _delete_event(client, tok, inst["id"], remaining_id)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] in _PARTIAL_STATUSES
    assert data["status"] != "paid"
    assert data["paid_amount"] is None
    assert data["paid_at"] is None
    assert data["payments"] == []


def test_delete_event_does_not_remove_next_instance(client):
    tok = register_and_login(client, "ledger_del_next@test.com")
    bill_id = _create_bill(client, tok)
    inst = _seed_instance(client, tok, bill_id)

    r = _add_payment(client, tok, inst["id"], "120.00")
    assert r.status_code == 200, r.text
    payment_id = r.json()["payments"][0]["id"]
    next_month = _next_period(inst["period"])
    assert len(_instances_for_bill_in_month(client, tok, bill_id, next_month)) == 1

    r = _delete_event(client, tok, inst["id"], payment_id)
    assert r.status_code == 200, r.text
    assert r.json()["status"] in _PARTIAL_STATUSES
    # The auto-generated next instance is not rolled back.
    assert len(_instances_for_bill_in_month(client, tok, bill_id, next_month)) == 1


def test_delete_event_from_other_instance_returns_404(client):
    tok = register_and_login(client, "ledger_del_404@test.com")
    bill_id_a = _create_bill(client, tok)
    bill_id_b = _create_bill(client, tok, {"name": "Water"})
    inst_a = _seed_instance(client, tok, bill_id_a)
    inst_b = _seed_instance(client, tok, bill_id_b)

    r = _add_payment(client, tok, inst_a["id"], "10.00")
    assert r.status_code == 200, r.text
    payment_id = r.json()["payments"][0]["id"]

    r = _delete_event(client, tok, inst_b["id"], payment_id)
    assert r.status_code == 404

    r = _delete_event(client, tok, inst_a["id"], 999999)
    assert r.status_code == 404


def test_delete_event_cross_user_returns_403(client):
    tok_a = register_and_login(client, "ledger_del_a@test.com")
    tok_b = register_and_login(client, "ledger_del_b@test.com")
    bill_id = _create_bill(client, tok_a)
    inst = _seed_instance(client, tok_a, bill_id)

    r = _add_payment(client, tok_a, inst["id"], "10.00")
    assert r.status_code == 200, r.text
    payment_id = r.json()["payments"][0]["id"]

    r = _delete_event(client, tok_b, inst["id"], payment_id)
    assert r.status_code == 403


def test_add_payment_other_user_returns_403(client):
    tok_a = register_and_login(client, "ledger_add_a@test.com")
    tok_b = register_and_login(client, "ledger_add_b@test.com")
    bill_id = _create_bill(client, tok_a)
    inst = _seed_instance(client, tok_a, bill_id)

    r = _add_payment(client, tok_b, inst["id"], "10.00")
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Unpay
# ---------------------------------------------------------------------------


def test_unpay_clears_all_events(client):
    tok = register_and_login(client, "ledger_unpay@test.com")
    bill_id = _create_bill(client, tok)
    inst = _seed_instance(client, tok, bill_id)

    _add_payment(client, tok, inst["id"], "50.00", note="part 1")
    _add_payment(client, tok, inst["id"], "70.00", note="part 2")

    r = client.post(f"/bills/payments/{inst['id']}/unpay", headers=auth(tok))
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["payments"] == []
    assert data["paid_amount"] is None
    assert data["paid_at"] is None
    assert data["status"] in _PARTIAL_STATUSES
    assert data["status"] != "paid"

    listed = _instances_for_bill_in_month(client, tok, bill_id, inst["period"])
    assert listed[0]["payments"] == []


def test_unpay_partial_instance_returns_400_and_keeps_events(client):
    tok = register_and_login(client, "ledger_unpay_partial@test.com")
    bill_id = _create_bill(client, tok)
    inst = _seed_instance(client, tok, bill_id)

    _add_payment(client, tok, inst["id"], "50.00")

    r = client.post(f"/bills/payments/{inst['id']}/unpay", headers=auth(tok))
    assert r.status_code == 400

    listed = _instances_for_bill_in_month(client, tok, bill_id, inst["period"])
    assert len(listed[0]["payments"]) == 1


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("amount", ["0", "-5.00"])
def test_payment_amount_must_be_positive(client, amount: str):
    tok = register_and_login(client, "ledger_invalid_amount@test.com")
    bill_id = _create_bill(client, tok)
    inst = _seed_instance(client, tok, bill_id)

    r = _add_payment(client, tok, inst["id"], amount)
    assert r.status_code == 422


def test_payment_missing_amount_returns_422(client):
    tok = register_and_login(client, "ledger_missing_amount@test.com")
    bill_id = _create_bill(client, tok)
    inst = _seed_instance(client, tok, bill_id)

    r = client.post(
        f"/bills/payments/{inst['id']}/payments",
        json={"paid_on": None, "note": None},
        headers=auth(tok),
    )
    assert r.status_code == 422


def test_payment_future_paid_on_returns_422(client):
    tok = register_and_login(client, "ledger_future@test.com")
    bill_id = _create_bill(client, tok)
    inst = _seed_instance(client, tok, bill_id)

    too_far = (date.today() + timedelta(days=2)).isoformat()
    r = _add_payment(client, tok, inst["id"], "10.00", paid_on=too_far)
    assert r.status_code == 422


def test_payment_paid_on_tomorrow_allowed_for_timezone_slack(client):
    """A user ahead of UTC can legitimately be a calendar day ahead."""
    tok = register_and_login(client, "ledger_tz@test.com")
    bill_id = _create_bill(client, tok)
    inst = _seed_instance(client, tok, bill_id)

    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    r = _add_payment(client, tok, inst["id"], "10.00", paid_on=tomorrow)
    assert r.status_code == 200, r.text
    assert r.json()["payments"][0]["paid_on"] == tomorrow


# ---------------------------------------------------------------------------
# Legacy /pay compatibility
# ---------------------------------------------------------------------------


def test_legacy_pay_default_records_remaining_and_is_idempotent(client):
    tok = register_and_login(client, "ledger_legacy@test.com")
    bill_id = _create_bill(client, tok)
    inst = _seed_instance(client, tok, bill_id)
    next_month = _next_period(inst["period"])

    r = _legacy_pay(client, tok, inst["id"], notes="legacy note")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "paid"
    assert Decimal(str(data["paid_amount"])) == Decimal("120.00")
    assert len(data["payments"]) == 1
    payment = data["payments"][0]
    assert Decimal(str(payment["amount"])) == Decimal("120.00")
    assert payment["paid_on"] == date.today().isoformat()
    assert payment["note"] == "legacy note"
    assert len(_instances_for_bill_in_month(client, tok, bill_id, next_month)) == 1

    # Retry must not create a duplicate event or next instance.
    r = _legacy_pay(client, tok, inst["id"], notes="legacy note")
    assert r.status_code == 200, r.text
    data = r.json()
    assert len(data["payments"]) == 1
    assert len(_instances_for_bill_in_month(client, tok, bill_id, next_month)) == 1


def test_legacy_pay_partial_then_default_completes(client):
    tok = register_and_login(client, "ledger_legacy_partial@test.com")
    bill_id = _create_bill(client, tok)
    inst = _seed_instance(client, tok, bill_id)

    r1 = _legacy_pay(client, tok, inst["id"], paid_amount=30.00, notes="first")
    assert r1.status_code == 200, r1.text
    d1 = r1.json()
    assert d1["status"] in _PARTIAL_STATUSES
    assert d1["status"] != "paid"
    assert Decimal(str(d1["paid_amount"])) == Decimal("30.00")

    r2 = _legacy_pay(client, tok, inst["id"])
    assert r2.status_code == 200, r2.text
    d2 = r2.json()
    assert d2["status"] == "paid"
    assert Decimal(str(d2["paid_amount"])) == Decimal("120.00")
    assert len(d2["payments"]) == 2
    assert Decimal(str(d2["payments"][1]["amount"])) == Decimal("90.00")
