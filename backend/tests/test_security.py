"""Security-hardening tests: rate limits, password policy, token revocation,
JWT claims, and secure cookies."""

import hashlib
from unittest.mock import patch

from app.core.config import settings
from app.core.ratelimit import reset_rate_limits
from app.core.security import decode_token
from app.models.reset_token import PasswordResetToken
from tests.conftest import auth, register_and_login


def _token_hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


def test_login_rate_limited_returns_429(client):
    original = settings.login_rate_limit
    try:
        settings.login_rate_limit = 3
        reset_rate_limits("login")
        for _ in range(3):
            r = client.post(
                "/auth/login",
                json={"email": "nobody@test.com", "password": "wrong"},
            )
            assert r.status_code == 401
        r = client.post(
            "/auth/login",
            json={"email": "nobody@test.com", "password": "wrong"},
        )
        assert r.status_code == 429
    finally:
        settings.login_rate_limit = original
        reset_rate_limits()


def test_register_rate_limited_returns_429(client):
    original = settings.register_rate_limit
    try:
        settings.register_rate_limit = 1
        reset_rate_limits("register")
        r = client.post(
            "/auth/register",
            json={"email": "rl1@test.com", "password": "pw123456"},
        )
        assert r.status_code == 201
        r = client.post(
            "/auth/register",
            json={"email": "rl2@test.com", "password": "pw123456"},
        )
        assert r.status_code == 429
    finally:
        settings.register_rate_limit = original
        reset_rate_limits("register")


def test_rate_limit_uses_forwarded_for_when_trusting_proxy(client):
    original_limit = settings.login_rate_limit
    original_proxy = settings.trust_proxy
    try:
        settings.trust_proxy = True
        settings.login_rate_limit = 1
        reset_rate_limits("login")
        r = client.post(
            "/auth/login",
            json={"email": "nobody@test.com", "password": "wrong"},
            headers={"X-Forwarded-For": "1.2.3.4"},
        )
        assert r.status_code == 401
        # Different IP → its own bucket → not limited yet.
        r = client.post(
            "/auth/login",
            json={"email": "nobody@test.com", "password": "wrong"},
            headers={"X-Forwarded-For": "5.6.7.8"},
        )
        assert r.status_code == 401
        # Same IP as the first request → bucket is now full.
        r = client.post(
            "/auth/login",
            json={"email": "nobody@test.com", "password": "wrong"},
            headers={"X-Forwarded-For": "1.2.3.4"},
        )
        assert r.status_code == 429
    finally:
        settings.trust_proxy = original_proxy
        settings.login_rate_limit = original_limit
        reset_rate_limits("login")


def test_send_now_rate_limited_by_user_returns_429(client):
    token = register_and_login(client, "sendnowrl@test.com")
    original = settings.send_now_rate_limit
    try:
        settings.send_now_rate_limit = 1
        reset_rate_limits("send_now")
        # SMTP not configured → 400, but the dependency already counted the request.
        r = client.post("/auth/send-notification-now", headers=auth(token))
        assert r.status_code == 400
        r = client.post("/auth/send-notification-now", headers=auth(token))
        assert r.status_code == 429
    finally:
        settings.send_now_rate_limit = original
        reset_rate_limits("send_now")


# ---------------------------------------------------------------------------
# Password policy
# ---------------------------------------------------------------------------


def test_password_policy_rejects_common_password(client):
    r = client.post(
        "/auth/register",
        json={"email": "common@test.com", "password": "password"},
    )
    assert r.status_code == 422


def test_password_policy_rejects_short_password(client):
    r = client.post(
        "/auth/register",
        json={"email": "short@test.com", "password": "short"},
    )
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Token versioning / revocation
# ---------------------------------------------------------------------------


def test_change_password_revokes_old_token(client):
    token = register_and_login(client, "chpwr@test.com")
    r = client.get("/auth/me", headers=auth(token))
    assert r.status_code == 200

    r = client.patch(
        "/auth/change-password",
        json={"current_password": "pw123456", "new_password": "newpassword1"},
        headers=auth(token),
    )
    assert r.status_code == 200

    r = client.get("/auth/me", headers=auth(token))
    assert r.status_code == 401

    login_r = client.post(
        "/auth/login",
        json={"email": "chpwr@test.com", "password": "newpassword1"},
    )
    assert login_r.status_code == 200


def test_logout_revokes_token(client):
    token = register_and_login(client, "logoutrev@test.com")
    r = client.post("/auth/logout", headers=auth(token))
    assert r.status_code == 204

    r = client.get("/auth/me", headers=auth(token))
    assert r.status_code == 401


def test_reset_password_revokes_old_token(client_db):
    client, db = client_db
    token = register_and_login(client, "resetrev@example.com")

    with patch("app.routers.auth.send_password_reset_email"):
        client.post("/auth/forgot-password", json={"email": "resetrev@example.com"})

    known_raw = "known-raw-token-for-testing-12345"
    row = db.query(PasswordResetToken).one()
    row.token_hash = _token_hash(known_raw)
    db.commit()

    r = client.post(
        "/auth/reset-password",
        json={"token": known_raw, "new_password": "newpassword1"},
    )
    assert r.status_code == 200

    r = client.get("/auth/me", headers=auth(token))
    assert r.status_code == 401

    login_r = client.post(
        "/auth/login",
        json={"email": "resetrev@example.com", "password": "newpassword1"},
    )
    assert login_r.status_code == 200


# ---------------------------------------------------------------------------
# JWT claims & cookies
# ---------------------------------------------------------------------------


def test_jwt_contains_security_claims(client):
    r = client.post(
        "/auth/register",
        json={"email": "claims@test.com", "password": "pw123456"},
    )
    assert r.status_code == 201
    payload = decode_token(r.json()["access_token"])
    assert payload["iss"] == "pay-tracker-backend"
    assert payload["aud"] == "pay-tracker"
    assert payload["iat"]
    assert payload["exp"]
    assert payload["jti"]
    assert payload["tv"] == 0


def test_secure_cookie_set_when_enabled(client):
    original = settings.cookie_secure
    try:
        settings.cookie_secure = True
        r = client.post(
            "/auth/register",
            json={"email": "secure@test.com", "password": "pw123456"},
        )
        assert r.status_code == 201
        assert "secure" in r.headers.get("set-cookie", "").lower()
    finally:
        settings.cookie_secure = original
