"""Integration tests for forgot-password / reset-password / smtp-status endpoints."""

import hashlib
import smtplib
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.reset_token import PasswordResetToken
from tests.conftest import auth, register_and_login


def _token_hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


# ---------------------------------------------------------------------------
# smtp-status
# ---------------------------------------------------------------------------


def test_smtp_status_unconfigured(client_db):
    client, _ = client_db
    with patch("app.routers.auth.settings") as mock_settings:
        mock_settings.smtp_host = None
        r = client.get("/auth/smtp-status")
    assert r.status_code == 200
    assert r.json() == {"configured": False}


def test_smtp_status_configured(client_db):
    client, _ = client_db
    with patch("app.routers.auth.settings") as mock_settings:
        mock_settings.smtp_host = "smtp.example.com"
        r = client.get("/auth/smtp-status")
    assert r.status_code == 200
    assert r.json() == {"configured": True}


# ---------------------------------------------------------------------------
# forgot-password
# ---------------------------------------------------------------------------


def test_forgot_password_unknown_email_returns_200(client_db):
    client, _ = client_db
    r = client.post("/auth/forgot-password", json={"email": "nobody@example.com"})
    assert r.status_code == 200
    assert "reset link" in r.json()["message"]


def test_forgot_password_creates_token_row(client_db):
    client, db = client_db
    register_and_login(client, "user@example.com")

    with patch("app.routers.auth.send_password_reset_email"):
        r = client.post("/auth/forgot-password", json={"email": "user@example.com"})

    assert r.status_code == 200
    rows = db.query(PasswordResetToken).all()
    assert len(rows) == 1


def test_forgot_password_replaces_old_token(client_db):
    client, db = client_db
    register_and_login(client, "user2@example.com")

    with patch("app.routers.auth.send_password_reset_email"):
        client.post("/auth/forgot-password", json={"email": "user2@example.com"})
        first_hash = db.query(PasswordResetToken).one().token_hash

        client.post("/auth/forgot-password", json={"email": "user2@example.com"})

    rows = db.query(PasswordResetToken).all()
    assert len(rows) == 1
    assert rows[0].token_hash != first_hash


# ---------------------------------------------------------------------------
# reset-password
# ---------------------------------------------------------------------------


def test_reset_password_success(client_db):
    client, db = client_db
    register_and_login(client, "reset@example.com")

    with patch("app.routers.auth.send_password_reset_email"):
        client.post("/auth/forgot-password", json={"email": "reset@example.com"})

    row = db.query(PasswordResetToken).one()
    # Reconstruct a valid raw token by brute-forcing is not possible; instead
    # insert a known token directly and call reset with it.
    known_raw = "known-raw-token-for-testing-12345"
    row.token_hash = _token_hash(known_raw)
    db.commit()

    r = client.post(
        "/auth/reset-password",
        json={"token": known_raw, "new_password": "newpassword1"},
    )
    assert r.status_code == 200

    # Token row is deleted after use.
    db.expire_all()
    assert db.query(PasswordResetToken).count() == 0

    # Login with new password succeeds.
    login_r = client.post(
        "/auth/login", json={"email": "reset@example.com", "password": "newpassword1"}
    )
    assert login_r.status_code == 200


def test_reset_password_invalid_token_returns_400(client_db):
    client, _ = client_db
    r = client.post(
        "/auth/reset-password",
        json={"token": "completely-bogus-token", "new_password": "newpassword1"},
    )
    assert r.status_code == 400


def test_reset_password_expired_token_returns_400(client_db):
    client, db = client_db
    register_and_login(client, "expired@example.com")

    with patch("app.routers.auth.send_password_reset_email"):
        client.post("/auth/forgot-password", json={"email": "expired@example.com"})

    known_raw = "expired-raw-token-for-testing-99"
    row = db.query(PasswordResetToken).one()
    row.token_hash = _token_hash(known_raw)
    row.expires_at = datetime.now(timezone.utc) - timedelta(hours=2)
    db.commit()

    r = client.post(
        "/auth/reset-password",
        json={"token": known_raw, "new_password": "newpassword1"},
    )
    assert r.status_code == 400
    assert "expired" in r.json()["detail"].lower()


def test_reset_password_too_short_returns_400(client_db):
    client, db = client_db
    register_and_login(client, "short@example.com")

    known_raw = "short-password-test-token-99999"
    db.add(
        PasswordResetToken(
            user_id=db.execute(
                __import__("sqlalchemy").text(
                    "SELECT id FROM users WHERE email='short@example.com'"
                )
            ).scalar(),
            token_hash=_token_hash(known_raw),
            expires_at=None,
        )
    )
    db.commit()

    r = client.post(
        "/auth/reset-password",
        json={"token": known_raw, "new_password": "short"},
    )
    assert r.status_code == 400
    assert "8" in r.json()["detail"]


def test_reset_password_token_is_single_use(client_db):
    client, db = client_db
    register_and_login(client, "singleuse@example.com")

    with patch("app.routers.auth.send_password_reset_email"):
        client.post("/auth/forgot-password", json={"email": "singleuse@example.com"})

    known_raw = "single-use-raw-token-for-testing"
    row = db.query(PasswordResetToken).one()
    row.token_hash = _token_hash(known_raw)
    db.commit()

    first = client.post(
        "/auth/reset-password",
        json={"token": known_raw, "new_password": "newpassword1"},
    )
    assert first.status_code == 200

    second = client.post(
        "/auth/reset-password",
        json={"token": known_raw, "new_password": "anotherpassword1"},
    )
    assert second.status_code == 400


def test_forgot_password_smtp_failure_still_returns_200(
    client_db: tuple[TestClient, Session],
) -> None:
    """SMTP exception must not propagate — enumeration guarantee must hold."""
    client, db = client_db
    register_and_login(client, "smtpfail@example.com", "pw-smtp-fail-1")

    with (
        patch("app.routers.auth.settings") as mock_settings,
        patch(
            "app.routers.auth.send_password_reset_email",
            side_effect=smtplib.SMTPException("connection refused"),
        ),
    ):
        mock_settings.smtp_host = "smtp.example.com"
        mock_settings.smtp_port = 587
        mock_settings.smtp_user = None
        mock_settings.smtp_password = None
        mock_settings.smtp_use_tls = True
        mock_settings.reminder_from = ""
        mock_settings.app_base_url = "http://localhost:3010"
        mock_settings.password_reset_token_expire_minutes = 60

        resp = client.post(
            "/auth/forgot-password", json={"email": "smtpfail@example.com"}
        )

    assert resp.status_code == 200
    assert "reset link" in resp.json()["message"].lower()
