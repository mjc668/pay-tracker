# Apprise Notifications Implementation Plan

## Overview

Add an Apprise API channel to the existing notification pipeline (bill reminders, monthly summary). Apprise is tried first when configured; email is the fallback. Settings shows whether Apprise is configured and can send a test notification.

## Configuration (env)

All in `backend/app/core/config.py` (`Settings`), documented in `.env.example`:

| Env var | Setting | Default | Meaning |
|---|---|---|---|
| `APPRISE_BASE_URL` | `apprise_base_url: str \| None` | `None` | e.g. `http://10.112.200.5:8000` (no trailing slash required; strip trailing `/`) |
| `APPRISE_URLS` | `apprise_urls: str \| None` | `None` | stateless mode: space/comma-separated Apprise target URLs, passed through as-is |
| `APPRISE_KEY` | `apprise_key: str \| None` | `None` | stateful mode: config key stored in the Apprise container |
| `APPRISE_TIMEOUT_SECONDS` | `apprise_timeout_seconds: float` | `10.0` | HTTP timeout |

- `Settings.apprise_configured` property: `bool(apprise_base_url) and bool(apprise_key or apprise_urls)`.
- `APPRISE_KEY` wins over `APPRISE_URLS` when both are set.
- The backend already runs with `env_file: .env` in compose, so no compose changes are needed; document that the apprise container must be reachable from the backend container (host IP or shared network).

## Dispatcher — `backend/app/services/notifications.py` (new)

```python
class NotificationChannel(str, Enum):
    apprise = "apprise"
    email = "email"

@dataclass(frozen=True)
class DeliveryResult:
    ok: bool
    channel: NotificationChannel | None = None
    error: str | None = None

def apprise_configured() -> bool
def any_channel_configured() -> bool            # apprise_configured() or settings.smtp_host
def send_via_apprise(*, title: str, body: str, notify_type: str = "info") -> DeliveryResult
def deliver(*, title: str, body: str, notify_type: str, email_sender: Callable[[], None]) -> DeliveryResult
```

`send_via_apprise` uses `httpx` (already a dependency):
- Stateful: `POST {base}/notify/{key}` JSON `{"title": ..., "body": ..., "type": notify_type}`.
- Stateless: `POST {base}/notify` JSON `{"urls": settings.apprise_urls, "title": ..., "body": ..., "type": notify_type}`.
- `notify_type` ∈ `info|success|warning|failure` (Apprise API values).
- 2xx → ok; non-2xx → `DeliveryResult(ok=False, error="apprise HTTP <code>")`; `httpx.HTTPError` → `error=str(exc)`.
- Never raises.

`deliver`:
1. If `apprise_configured()`: try Apprise. On success return it.
2. On Apprise failure/unconfigured: if `settings.smtp_host`, call `email_sender()` (which does the SMTP send) and return `channel=email`; catch `smtplib.SMTPException`/`OSError` → `ok=False, error=...`.
3. No channel configured → `ok=False, error="no notification channel configured"`.

Log every fallback at warning level (`logger.warning`).

## Message builders (plain text for Apprise)

Add to `backend/app/services/email.py` (or a small helper module) functions that produce `(title, body_text)` localized in en/pl/de, reusing existing copy:
- `build_reminder_text(*, bill_name, due_date, amount, currency, kind, language) -> tuple[str, str]` — kind ∈ `2_days_before|upcoming|on_day|1_day_after`.
- `build_monthly_summary_text(*, month_label, paid_rows, unpaid_rows, language) -> tuple[str, str]` — compact text version (totals + rows), not the full HTML.

Keep the existing HTML email functions untouched.

## Integration — `backend/app/services/reminder_job.py`

- `send_daily_reminders` / `send_catchup_reminders`: replace the `settings.smtp_host is None` early return with `not notifications.any_channel_configured()` (log "no notification channel configured, skipping").
- `send_monthly_summary_for_user`: replace the `if not settings.smtp_host: return False` gate with `if not any_channel_configured(): return False`. Build `title/body` via `build_monthly_summary_text`, then `deliver(..., notify_type="info", email_sender=<existing HTML send call>)`.
- `_send_and_flag`: remove the SMTP assert. Build `(title, body)` via `build_reminder_text` with `notify_type="warning"`; call `deliver(...)` with the existing `send_reminder_email(...)` call as `email_sender`. On `ok`:
  - set the reminder flag (`setattr(instance, flag_attr, True)`);
  - set `instance.email_sent_at = now(UTC)` **only when `result.channel == email`** (the field means "email sent"; Apprise deliveries keep it null);
  - commit; on commit failure log critical and return False (existing behavior).
- Return value semantics unchanged: True when the reminder was delivered (any channel).

## Auth endpoints — `backend/app/routers/auth.py`

- `GET /auth/smtp-status` unchanged (used for the forgot-password link).
- New `GET /auth/notification-status` → `NotificationStatusResponse {smtp_configured: bool, apprise_configured: bool}`.
- New `POST /auth/send-test-notification` → `SendTestNotificationOut {ok: bool, channel: str | None, detail: str | None}`; rate-limited with `rate_limited_by_user("send_now")`; sends title "Pay Tracker test notification" / body stating the channel works, through `deliver` with a simple `send_test_email` sender (add to `email.py`: plain-text-ish HTML email to `user.email`).
- `send-notification-now` / `send-monthly-summary-now`: replace the `settings.smtp_host is None` 400 with `not any_channel_configured()` → 400 `"No notification channel configured"`.

## Frontend

- `src/lib/user-api.ts` (or a new `notifications-api.ts`): `fetchNotificationStatus(): Promise<{smtp_configured: boolean; apprise_configured: boolean}>` and `sendTestNotification(): Promise<{ok: boolean; channel: string | null; detail: string | null}>`.
- `src/components/settings/EmailNotificationsTile.tsx`:
  - Show an "Apprise" status row (configured / not configured) next to the existing SMTP info, driven by `fetchNotificationStatus()`.
  - Add a "Send test notification" button that calls the endpoint and renders the result (e.g. "Sent via Apprise" / "Sent via email" / failure detail), following the existing inline result-text pattern.
  - Update the "no channel configured" messaging if it currently keys off SMTP only.
- i18n keys in all three locales (`SettingsPage.emailNotifications` or the existing namespace).
- No e2e required for the test button (needs a live apprise/SMTP); keep the existing settings spec passing. If a spec asserts SMTP-only gating, update it.

## Tests (backend)

New `tests/test_notifications_apprise.py` (monkeypatch `httpx.post`/`httpx.Client`, no network):
- stateless payload: URL `/notify`, body carries `urls`, `title`, `body`, `type`; key mode hits `/notify/{key}` and omits `urls`.
- Apprise 2xx → `deliver` returns apprise and does **not** call the email sender.
- Apprise 500 / timeout → falls back to email; email sender called; result channel email.
- No channels configured → `ok=False`; reminder job skips (`send_daily_reminders` early return).
- Reminder via Apprise sets the reminder flag but leaves `email_sent_at` null; reminder via email sets both.
- Monthly summary uses Apprise when configured.
- Endpoints: `notification-status` reflects settings; `send-test-notification` apprise-ok / fallback / none-configured; `send-notification-now` 400 only when no channel.
Extend `tests/test_reminder_job.py` only where gating changed (SMTP-configured cases must keep passing unchanged).

## Docs

- `.env.example`: add the `APPRISE_*` block with comments (stateful vs stateless, reachability note).
- `context/foundation/infrastructure.md`: short "Notification channels" section — Apprise preferred, email fallback, env table, example with a `caronc/apprise` sidecar and `APPRISE_URLS="ntfy://... discord://..."`.

## What We're NOT Doing

- No per-user Apprise targets (single household-wide env configuration).
- No new notification events (only reminders + monthly summary; test button is manual).
- No queue/retry system — Apprise failures fall back to email immediately; no background retries.
- No changes to browser notifications.
