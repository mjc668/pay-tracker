from typing import Annotated, Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.security import validate_password_strength


class RegisterRequest(BaseModel):
    email: EmailStr
    password: Annotated[str, Field(min_length=8)]

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        validate_password_strength(v)
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserProfileOut(BaseModel):
    model_config = {"from_attributes": True}

    email: EmailStr
    language_preference: str | None
    email_reminders_enabled: bool
    notify_2_days_before: bool
    notify_1_day_before: bool
    notify_on_day: bool
    notify_1_day_after: bool
    reminder_send_minute: int
    monthly_summary_enabled: bool


class UserProfileUpdate(BaseModel):
    language_preference: Literal["en", "pl", "de"] | None = None
    email_reminders_enabled: bool | None = None
    notify_2_days_before: bool | None = None
    notify_1_day_before: bool | None = None
    notify_on_day: bool | None = None
    notify_1_day_after: bool | None = None
    reminder_send_minute: Annotated[int, Field(ge=0, le=1410)] | None = None
    monthly_summary_enabled: bool | None = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        validate_password_strength(v)
        return v


class ChangeEmailRequest(BaseModel):
    new_email: EmailStr
    current_password: str


class SendNotificationNowOut(BaseModel):
    sent: int


class SendMonthlySummaryNowOut(BaseModel):
    sent: bool


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


class SmtpStatusResponse(BaseModel):
    configured: bool


class MessageResponse(BaseModel):
    message: str
