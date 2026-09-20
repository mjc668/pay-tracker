"""Tests for auth endpoints: GET /me, PATCH /me, PATCH /change-password,
PATCH /change-email, and 401 enforcement on protected routes."""

import pytest

from app.core.config import settings
from tests.conftest import auth, register_and_login

_PASSWORD = "pw123456"


# ---------------------------------------------------------------------------
# 401 — unauthenticated access to protected endpoints
# ---------------------------------------------------------------------------

_PROTECTED_ROUTES = [
    ("GET", "/auth/me"),
    ("PATCH", "/auth/me"),
    ("PATCH", "/auth/change-password"),
    ("PATCH", "/auth/change-email"),
    ("GET", "/bills"),
    ("POST", "/bills"),
    ("GET", "/bills/payments"),
    ("GET", "/export/json"),
    ("GET", "/export/xlsx"),
]


@pytest.mark.parametrize("method,path", _PROTECTED_ROUTES)
def test_unauthenticated_returns_401(client, method, path):
    r = client.request(method, path)
    assert r.status_code == 401, f"{method} {path} expected 401, got {r.status_code}"


def test_invalid_token_returns_401(client):
    r = client.get("/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# GET /auth/me
# ---------------------------------------------------------------------------


def test_get_me_returns_profile(client):
    token = register_and_login(client, "me@test.com", _PASSWORD)
    r = client.get("/auth/me", headers=auth(token))
    assert r.status_code == 200
    data = r.json()
    assert data["email"] == "me@test.com"
    assert "email_reminders_enabled" in data
    assert "notify_1_day_before" in data
    assert "monthly_summary_enabled" in data


# ---------------------------------------------------------------------------
# PATCH /auth/me
# ---------------------------------------------------------------------------


def test_patch_me_updates_language(client):
    token = register_and_login(client, "lang@test.com", _PASSWORD)
    r = client.patch(
        "/auth/me", json={"language_preference": "pl"}, headers=auth(token)
    )
    assert r.status_code == 200
    assert r.json()["language_preference"] == "pl"


def test_patch_me_updates_notification_flags(client):
    token = register_and_login(client, "notif@test.com", _PASSWORD)
    r = client.patch(
        "/auth/me",
        json={
            "email_reminders_enabled": True,
            "notify_2_days_before": True,
            "notify_on_day": True,
        },
        headers=auth(token),
    )
    assert r.status_code == 200
    data = r.json()
    assert data["email_reminders_enabled"] is True
    assert data["notify_2_days_before"] is True
    assert data["notify_on_day"] is True


def test_patch_me_disables_master_toggle_and_persists(client):
    """Disabling email_reminders_enabled persists to DB and is visible on GET /me."""
    token = register_and_login(client, "toggle_off@test.com", _PASSWORD)

    # New users default to enabled=True
    r = client.get("/auth/me", headers=auth(token))
    assert r.json()["email_reminders_enabled"] is True

    r = client.patch(
        "/auth/me", json={"email_reminders_enabled": False}, headers=auth(token)
    )
    assert r.status_code == 200
    assert r.json()["email_reminders_enabled"] is False

    # Re-fetch to confirm DB persistence (not just response echo)
    r = client.get("/auth/me", headers=auth(token))
    assert r.json()["email_reminders_enabled"] is False


def test_patch_me_invalid_language_returns_422(client):
    token = register_and_login(client, "badlang@test.com", _PASSWORD)
    r = client.patch(
        "/auth/me", json={"language_preference": "xx"}, headers=auth(token)
    )
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# PATCH /auth/me — default currency
# ---------------------------------------------------------------------------


def test_get_me_default_currency_starts_null(client):
    token = register_and_login(client, "currency_default@test.com", _PASSWORD)
    r = client.get("/auth/me", headers=auth(token))
    assert r.status_code == 200
    assert r.json()["default_currency"] is None


def test_patch_me_sets_default_currency_normalized(client):
    token = register_and_login(client, "currency@test.com", _PASSWORD)
    r = client.patch(
        "/auth/me", json={"default_currency": " eur "}, headers=auth(token)
    )
    assert r.status_code == 200
    assert r.json()["default_currency"] == "EUR"

    # Round-trip through GET to confirm DB persistence, not just an echo.
    r = client.get("/auth/me", headers=auth(token))
    assert r.status_code == 200
    assert r.json()["default_currency"] == "EUR"


def test_patch_me_clears_default_currency_with_explicit_null(client):
    token = register_and_login(client, "currency_clear@test.com", _PASSWORD)
    r = client.patch("/auth/me", json={"default_currency": "PLN"}, headers=auth(token))
    assert r.status_code == 200

    r = client.patch("/auth/me", json={"default_currency": None}, headers=auth(token))
    assert r.status_code == 200
    assert r.json()["default_currency"] is None

    r = client.get("/auth/me", headers=auth(token))
    assert r.json()["default_currency"] is None


@pytest.mark.parametrize("value", ["A", "TOOLONGVALUE", "US D", "EU-R", "   ", "€"])
def test_patch_me_invalid_default_currency_returns_422(client, value):
    token = register_and_login(client, "currency_bad@test.com", _PASSWORD)
    r = client.patch("/auth/me", json={"default_currency": value}, headers=auth(token))
    assert r.status_code == 422, value


# ---------------------------------------------------------------------------
# PATCH /auth/change-password
# ---------------------------------------------------------------------------


def test_change_password_success(client):
    token = register_and_login(client, "chpw@test.com", _PASSWORD)
    r = client.patch(
        "/auth/change-password",
        json={
            "current_password": _PASSWORD,
            "new_password": "newpassword1",
        },
        headers=auth(token),
    )
    assert r.status_code == 200

    # Old token still works (JWT is stateless), but new password lets us log in
    login_r = client.post(
        "/auth/login", json={"email": "chpw@test.com", "password": "newpassword1"}
    )
    assert login_r.status_code == 200


def test_change_password_wrong_current_returns_401(client):
    token = register_and_login(client, "badpw@test.com", _PASSWORD)
    r = client.patch(
        "/auth/change-password",
        json={
            "current_password": "wrong-password",
            "new_password": "newpassword1",
        },
        headers=auth(token),
    )
    assert r.status_code == 401


def test_change_password_too_short_returns_422(client):
    token = register_and_login(client, "shortpw@test.com", _PASSWORD)
    r = client.patch(
        "/auth/change-password",
        json={"current_password": _PASSWORD, "new_password": "short"},
        headers=auth(token),
    )
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# PATCH /auth/change-email
# ---------------------------------------------------------------------------


def test_change_email_success(client):
    token = register_and_login(client, "oldemail@test.com", _PASSWORD)
    r = client.patch(
        "/auth/change-email",
        json={"new_email": "newemail@test.com", "current_password": _PASSWORD},
        headers=auth(token),
    )
    assert r.status_code == 200
    assert r.json()["email"] == "newemail@test.com"


def test_change_email_wrong_password_returns_401(client):
    token = register_and_login(client, "emailpw@test.com", _PASSWORD)
    r = client.patch(
        "/auth/change-email",
        json={"new_email": "new@test.com", "current_password": "wrongpass"},
        headers=auth(token),
    )
    assert r.status_code == 401


def test_change_email_already_taken_returns_409(client):
    tok_a = register_and_login(client, "taken_a@test.com", _PASSWORD)
    register_and_login(client, "taken_b@test.com", _PASSWORD)

    r = client.patch(
        "/auth/change-email",
        json={"new_email": "taken_b@test.com", "current_password": _PASSWORD},
        headers=auth(tok_a),
    )
    assert r.status_code == 409


# ---------------------------------------------------------------------------
# POST /auth/register — error paths
# ---------------------------------------------------------------------------


def test_register_duplicate_email_returns_409(client):
    register_and_login(client, "dup@test.com", _PASSWORD)
    r = client.post(
        "/auth/register", json={"email": "dup@test.com", "password": _PASSWORD}
    )
    assert r.status_code == 409
    assert "already" in r.json()["detail"].lower()


def test_register_invalid_email_returns_422(client):
    r = client.post(
        "/auth/register", json={"email": "not-an-email", "password": _PASSWORD}
    )
    assert r.status_code == 422


def test_register_password_too_short_returns_422(client):
    r = client.post(
        "/auth/register", json={"email": "shortpw@test.com", "password": "short"}
    )
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# POST /auth/login — error paths
# ---------------------------------------------------------------------------


def test_login_wrong_password_returns_401(client):
    register_and_login(client, "loginpw@test.com", _PASSWORD)
    r = client.post(
        "/auth/login",
        json={"email": "loginpw@test.com", "password": "wrong-password"},
    )
    assert r.status_code == 401


def test_login_unknown_email_returns_401(client):
    r = client.post(
        "/auth/login",
        json={"email": "nobody@test.com", "password": _PASSWORD},
    )
    assert r.status_code == 401


def test_login_missing_fields_returns_422(client):
    r = client.post("/auth/login", json={"email": "missing@test.com"})
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# POST /auth/send-notification-now
# ---------------------------------------------------------------------------


def test_send_notification_no_smtp_returns_400(client):
    from unittest.mock import patch

    token = register_and_login(client, "notif_nosmtp@test.com", _PASSWORD)
    with (
        patch.object(settings, "smtp_host", None),
        patch.object(settings, "apprise_base_url", None),
        patch.object(settings, "apprise_urls", None),
        patch.object(settings, "apprise_key", None),
    ):
        r = client.post("/auth/send-notification-now", headers=auth(token))
    assert r.status_code == 400


def test_send_notification_reminders_disabled_returns_zero(client):
    from unittest.mock import patch

    token = register_and_login(client, "notif_off@test.com", _PASSWORD)
    client.patch(
        "/auth/me", json={"email_reminders_enabled": False}, headers=auth(token)
    )
    with patch.object(settings, "smtp_host", "smtp.test"):
        r = client.post("/auth/send-notification-now", headers=auth(token))
    assert r.status_code == 200
    assert r.json()["sent"] == 0


def test_send_notification_calls_service_and_returns_count(client):
    from unittest.mock import patch

    token = register_and_login(client, "notif_ok@test.com", _PASSWORD)
    with (
        patch.object(settings, "smtp_host", "smtp.test"),
        patch("app.routers.auth.send_reminders_for_user", return_value=2) as mock_send,
    ):
        r = client.post("/auth/send-notification-now", headers=auth(token))
    assert r.status_code == 200
    assert r.json()["sent"] == 2
    mock_send.assert_called_once()


# ---------------------------------------------------------------------------
# POST /auth/send-monthly-summary-now
# ---------------------------------------------------------------------------


def test_send_monthly_summary_no_smtp_returns_400(client):
    from unittest.mock import patch

    token = register_and_login(client, "summary_nosmtp@test.com", _PASSWORD)
    with (
        patch.object(settings, "smtp_host", None),
        patch.object(settings, "apprise_base_url", None),
        patch.object(settings, "apprise_urls", None),
        patch.object(settings, "apprise_key", None),
    ):
        r = client.post("/auth/send-monthly-summary-now", headers=auth(token))
    assert r.status_code == 400


def test_send_monthly_summary_disabled_returns_false(client):
    from unittest.mock import patch

    token = register_and_login(client, "summary_off@test.com", _PASSWORD)
    client.patch(
        "/auth/me", json={"monthly_summary_enabled": False}, headers=auth(token)
    )
    with patch.object(settings, "smtp_host", "smtp.test"):
        r = client.post("/auth/send-monthly-summary-now", headers=auth(token))
    assert r.status_code == 200
    assert r.json()["sent"] is False


def test_send_monthly_summary_master_toggle_off_returns_false(client):
    """Master toggle (email_reminders_enabled=False) also blocks monthly summary."""
    from unittest.mock import patch

    token = register_and_login(client, "summary_master_off@test.com", _PASSWORD)
    # Disable master toggle only — monthly_summary_enabled stays True (default)
    client.patch(
        "/auth/me", json={"email_reminders_enabled": False}, headers=auth(token)
    )
    with patch.object(settings, "smtp_host", "smtp.test"):
        r = client.post("/auth/send-monthly-summary-now", headers=auth(token))
    assert r.status_code == 200
    assert r.json()["sent"] is False


def test_send_monthly_summary_calls_service(client):
    from unittest.mock import patch

    token = register_and_login(client, "summary_ok@test.com", _PASSWORD)
    with (
        patch.object(settings, "smtp_host", "smtp.test"),
        patch(
            "app.routers.auth.send_monthly_summary_for_user", return_value=True
        ) as mock_send,
    ):
        r = client.post("/auth/send-monthly-summary-now", headers=auth(token))
    assert r.status_code == 200
    assert r.json()["sent"] is True
    mock_send.assert_called_once()


def test_send_monthly_summary_now_does_not_set_flag(client_db):
    """Manual send must never touch monthly_summary_last_sent — only the cron does."""
    from unittest.mock import patch

    from app.models.user import User

    client, db = client_db
    token = register_and_login(client, "summary_flag@test.com", _PASSWORD)
    with (
        patch.object(settings, "smtp_host", "smtp.test"),
        patch("app.routers.auth.send_monthly_summary_for_user", return_value=True),
    ):
        r = client.post("/auth/send-monthly-summary-now", headers=auth(token))
    assert r.status_code == 200
    assert r.json()["sent"] is True

    from datetime import datetime, timezone

    current_month = datetime.now(timezone.utc).strftime("%Y-%m")
    db.expire_all()
    user = db.query(User).filter(User.email == "summary_flag@test.com").first()
    assert user.monthly_summary_last_sent != current_month
