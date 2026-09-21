import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone

_logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import current_user, optional_current_user
from app.core.ratelimit import rate_limited, rate_limited_by_user
from app.core.security import (
    create_access_token,
    hash_password,
    validate_password_strength,
    verify_password,
)
from app.models.reset_token import PasswordResetToken
from app.models.user import User
from app.schemas.auth import (
    ChangeEmailRequest,
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    NotificationStatusResponse,
    RegisterRequest,
    ResetPasswordRequest,
    SendMonthlySummaryNowOut,
    SendNotificationNowOut,
    SendTestNotificationOut,
    SmtpStatusResponse,
    TokenResponse,
    UserProfileOut,
    UserProfileUpdate,
)
from app.services import notifications
from app.services.categories import ensure_default_categories
from app.services.email import send_password_reset_email, send_test_email
from app.services.reminder_job import (
    send_monthly_summary_for_user,
    send_reminders_for_user,
)

router = APIRouter(prefix="/auth", tags=["auth"])

_TEST_NOTIFICATION_TITLE = "Pay Tracker test notification"
_TEST_NOTIFICATION_BODY = (
    "This is a test notification from Pay Tracker. "
    "If you can read this, notifications are working."
)


def _set_auth_cookie(response: Response, token: str) -> None:
    """Set the JWT as an HttpOnly cookie plus a non-HttpOnly presence flag."""
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
        max_age=settings.access_token_expire_minutes * 60,
    )
    # Non-HttpOnly presence flag so the frontend can detect login state without XSS risk.
    response.set_cookie(
        key="auth_logged_in",
        value="1",
        httponly=False,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
        max_age=settings.access_token_expire_minutes * 60,
    )


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(key="access_token", path="/")
    response.delete_cookie(key="auth_logged_in", path="/")


@router.post(
    "/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED
)
def register(
    body: RegisterRequest,
    response: Response,
    _rl: None = Depends(rate_limited("register")),
    db: Session = Depends(get_db),
):
    if db.query(User).filter(User.email == body.email).first():
        raise HTTPException(status_code=409, detail="Email already registered")
    user = User(email=body.email, password_hash=hash_password(body.password))
    db.add(user)
    db.flush()
    ensure_default_categories(db, user)
    db.commit()
    db.refresh(user)
    token = create_access_token(str(user.id), token_version=user.token_version)
    _set_auth_cookie(response, token)
    return TokenResponse(access_token=token)


@router.post("/login", response_model=TokenResponse)
def login(
    body: LoginRequest,
    response: Response,
    _rl: None = Depends(rate_limited("login")),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.email == body.email).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token(str(user.id), token_version=user.token_version)
    _set_auth_cookie(response, token)
    return TokenResponse(access_token=token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    user: User | None = Depends(optional_current_user),
    db: Session = Depends(get_db),
):
    # Must succeed even when the token is already dead (expired, revoked, or
    # rejected by the new issuer/audience checks): without this, a stale
    # HttpOnly cookie can never be cleared client-side and the proxy keeps
    # bouncing /login → /dashboard forever.
    if user is not None:
        user.token_version += 1
        db.commit()
    _clear_auth_cookies(response)


@router.get("/me", response_model=UserProfileOut)
def get_me(user: User = Depends(current_user)):
    return user


@router.patch("/me", response_model=UserProfileOut)
def update_me(
    body: UserProfileUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    # UserProfileUpdate is the security boundary — only fields declared there are patchable.
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    db.commit()
    db.refresh(user)
    return user


@router.delete("/users/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_me(
    response: Response,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    db.delete(user)
    db.commit()
    _clear_auth_cookies(response)


@router.patch("/change-password", status_code=status.HTTP_200_OK)
def change_password(
    body: ChangePasswordRequest,
    user: User = Depends(current_user),
    _rl: None = Depends(rate_limited_by_user("change_password")),
    db: Session = Depends(get_db),
):
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status_code=401, detail="Current password is incorrect")
    user.password_hash = hash_password(body.new_password)
    user.token_version += 1
    db.commit()


@router.post("/send-notification-now", response_model=SendNotificationNowOut)
def send_notification_now(
    user: User = Depends(current_user),
    _rl: None = Depends(rate_limited_by_user("send_now")),
    db: Session = Depends(get_db),
):
    if not notifications.any_channel_configured():
        raise HTTPException(
            status_code=400, detail="No notification channel configured"
        )
    if not user.email_reminders_enabled:
        return SendNotificationNowOut(sent=0)
    sent = send_reminders_for_user(db, user)
    return SendNotificationNowOut(sent=sent)


@router.post("/send-monthly-summary-now", response_model=SendMonthlySummaryNowOut)
def send_monthly_summary_now(
    user: User = Depends(current_user),
    _rl: None = Depends(rate_limited_by_user("send_now")),
    db: Session = Depends(get_db),
):
    if not notifications.any_channel_configured():
        raise HTTPException(
            status_code=400, detail="No notification channel configured"
        )
    if not user.email_reminders_enabled or not user.monthly_summary_enabled:
        return SendMonthlySummaryNowOut(sent=False)
    current_month = datetime.now(timezone.utc).strftime("%Y-%m")
    sent = send_monthly_summary_for_user(db, user, current_month)
    return SendMonthlySummaryNowOut(sent=sent)


@router.get("/server-time")
def server_time(_: User = Depends(current_user)):
    return {"server_time": datetime.now(timezone.utc).isoformat()}


@router.patch("/change-email", response_model=UserProfileOut)
def change_email(
    body: ChangeEmailRequest,
    user: User = Depends(current_user),
    _rl: None = Depends(rate_limited_by_user("change_email")),
    db: Session = Depends(get_db),
):
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status_code=401, detail="Current password is incorrect")
    existing = db.query(User).filter(User.email == body.new_email).first()
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")
    user.email = body.new_email
    user.token_version += 1
    db.commit()
    db.refresh(user)
    return user


@router.get("/smtp-status", response_model=SmtpStatusResponse)
def smtp_status():
    return SmtpStatusResponse(configured=settings.smtp_host is not None)


@router.get("/notification-status", response_model=NotificationStatusResponse)
def notification_status():
    return NotificationStatusResponse(
        smtp_configured=settings.smtp_host is not None,
        apprise_configured=notifications.apprise_configured(),
    )


@router.post("/send-test-notification", response_model=SendTestNotificationOut)
def send_test_notification(
    user: User = Depends(current_user),
    _rl: None = Depends(rate_limited_by_user("send_now")),
):
    def _send_email() -> None:
        smtp_host = settings.smtp_host
        if smtp_host is None:
            raise OSError("SMTP not configured")
        send_test_email(
            smtp_host=smtp_host,
            smtp_port=settings.smtp_port,
            smtp_user=settings.smtp_user,
            smtp_password=(
                settings.smtp_password.get_secret_value()
                if settings.smtp_password
                else None
            ),
            smtp_use_tls=settings.smtp_use_tls,
            from_addr=settings.reminder_from or settings.smtp_user or "",
            to_addr=user.email,
            language=user.language_preference or "en",
        )

    result = notifications.deliver(
        title=_TEST_NOTIFICATION_TITLE,
        body=_TEST_NOTIFICATION_BODY,
        notify_type="success",
        email_sender=_send_email,
    )
    return SendTestNotificationOut(
        ok=result.ok,
        channel=result.channel.value if result.channel else None,
        detail=result.error,
    )


_FORGOT_PASSWORD_RESPONSE = MessageResponse(
    message="If that email is registered, you'll receive a reset link shortly."
)


@router.post("/forgot-password", response_model=MessageResponse)
def forgot_password(
    body: ForgotPasswordRequest,
    _rl: None = Depends(rate_limited("forgot_password")),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.email == body.email).first()
    if not user:
        return _FORGOT_PASSWORD_RESPONSE

    # Invalidate any existing tokens for this user before issuing a new one.
    db.query(PasswordResetToken).filter(PasswordResetToken.user_id == user.id).delete()

    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

    if settings.password_reset_token_expire_minutes > 0:
        expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=settings.password_reset_token_expire_minutes
        )
    else:
        expires_at = None

    db.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
    )
    db.commit()

    if settings.smtp_host:
        reset_url = f"{settings.app_base_url}/reset-password?token={raw_token}"
        try:
            send_password_reset_email(
                smtp_host=settings.smtp_host,
                smtp_port=settings.smtp_port,
                smtp_user=settings.smtp_user,
                smtp_password=(
                    settings.smtp_password.get_secret_value()
                    if settings.smtp_password
                    else None
                ),
                smtp_use_tls=settings.smtp_use_tls,
                from_addr=settings.reminder_from or "",
                to_addr=user.email,
                reset_url=reset_url,
                language=user.language_preference or "en",
                expires_minutes=settings.password_reset_token_expire_minutes,
            )
        except Exception:
            _logger.exception("Failed to send password reset email to %s", user.email)

    return _FORGOT_PASSWORD_RESPONSE


@router.post("/reset-password", response_model=MessageResponse)
def reset_password(
    body: ResetPasswordRequest,
    _rl: None = Depends(rate_limited("reset_password")),
    db: Session = Depends(get_db),
):
    token_hash = hashlib.sha256(body.token.encode()).hexdigest()
    token_row = (
        db.query(PasswordResetToken)
        .filter(PasswordResetToken.token_hash == token_hash)
        .first()
    )
    if not token_row:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    if token_row.expires_at and token_row.expires_at < datetime.now(timezone.utc):
        db.delete(token_row)
        db.commit()
        raise HTTPException(status_code=400, detail="Reset token has expired")

    try:
        validate_password_strength(body.new_password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    user = db.query(User).filter(User.id == token_row.user_id).first()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    user.password_hash = hash_password(body.new_password)
    user.token_version += 1
    db.delete(token_row)
    db.commit()

    return MessageResponse(message="Password updated successfully.")
