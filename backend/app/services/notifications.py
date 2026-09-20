import logging
import smtplib
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class NotificationChannel(str, Enum):
    apprise = "apprise"
    email = "email"


@dataclass(frozen=True)
class DeliveryResult:
    ok: bool
    channel: NotificationChannel | None = None
    error: str | None = None


def apprise_configured() -> bool:
    return settings.apprise_configured


def any_channel_configured() -> bool:
    return apprise_configured() or bool(settings.smtp_host)


def send_via_apprise(
    *, title: str, body: str, notify_type: str = "info"
) -> DeliveryResult:
    if not apprise_configured():
        return DeliveryResult(ok=False, error="apprise not configured")

    base_url = (settings.apprise_base_url or "").rstrip("/")
    if settings.apprise_key:
        url = f"{base_url}/notify/{settings.apprise_key}"
        payload: dict[str, str | None] = {
            "title": title,
            "body": body,
            "type": notify_type,
        }
    else:
        url = f"{base_url}/notify"
        payload = {
            "urls": settings.apprise_urls,
            "title": title,
            "body": body,
            "type": notify_type,
        }

    try:
        response = httpx.post(
            url, json=payload, timeout=settings.apprise_timeout_seconds
        )
    except httpx.HTTPError as exc:
        return DeliveryResult(ok=False, error=str(exc))

    if response.is_success:
        return DeliveryResult(ok=True, channel=NotificationChannel.apprise)
    return DeliveryResult(ok=False, error=f"apprise HTTP {response.status_code}")


def deliver(
    *,
    title: str,
    body: str,
    notify_type: str,
    email_sender: Callable[[], None],
) -> DeliveryResult:
    apprise_result: DeliveryResult | None = None
    if apprise_configured():
        apprise_result = send_via_apprise(
            title=title, body=body, notify_type=notify_type
        )
        if apprise_result.ok:
            return apprise_result
        logger.warning(
            "Apprise delivery failed (%s); falling back to email",
            apprise_result.error,
        )

    if settings.smtp_host:
        try:
            email_sender()
        except (smtplib.SMTPException, OSError) as exc:
            logger.warning("Email delivery failed: %s", exc)
            return DeliveryResult(ok=False, error=str(exc))
        return DeliveryResult(ok=True, channel=NotificationChannel.email)

    if apprise_result is not None:
        logger.warning(
            "Apprise delivery failed and no email channel is configured: %s",
            apprise_result.error,
        )
        return apprise_result
    return DeliveryResult(ok=False, error="no notification channel configured")
