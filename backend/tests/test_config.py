"""Settings-level guards for insecure or self-defeating configuration."""

import warnings

from app.core.config import Settings


def _warnings_for(**overrides) -> list[str]:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        Settings(**overrides)
    return [str(w.message) for w in caught]


def test_secure_cookie_over_http_warns():
    messages = _warnings_for(
        cookie_secure=True, app_base_url="http://10.112.200.5:3010"
    )
    assert any("COOKIE_SECURE=true" in m for m in messages)


def test_secure_cookie_over_https_does_not_warn():
    messages = _warnings_for(cookie_secure=True, app_base_url="https://pay.example.com")
    assert not any("COOKIE_SECURE=true" in m for m in messages)


def test_secure_cookie_on_localhost_does_not_warn():
    messages = _warnings_for(cookie_secure=True, app_base_url="http://localhost:3010")
    assert not any("COOKIE_SECURE=true" in m for m in messages)


def test_insecure_cookie_over_http_does_not_warn():
    messages = _warnings_for(
        cookie_secure=False, app_base_url="http://10.112.200.5:3010"
    )
    assert not any("COOKIE_SECURE=true" in m for m in messages)


def test_apprise_base_url_trailing_slashes_are_stripped():
    s = Settings(apprise_base_url="http://10.112.200.5:8000///")
    assert s.apprise_base_url == "http://10.112.200.5:8000"


def test_apprise_configured_needs_only_a_base_url():
    assert Settings(apprise_base_url=None).apprise_configured is False
    assert Settings(apprise_base_url="http://x").apprise_configured is True
    assert (
        Settings(
            apprise_base_url="http://x", apprise_urls="ntfy://topic"
        ).apprise_configured
        is True
    )
    assert (
        Settings(
            apprise_base_url="http://x", apprise_key="household"
        ).apprise_configured
        is True
    )
