import os
import warnings
from urllib.parse import urlparse

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEFAULT_JWT_SECRET = "changeme-use-a-long-random-string"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file="../.env", extra="ignore")

    database_url: str = "postgresql://paytracker:changeme@localhost:5432/paytracker"

    environment: str = "development"
    cookie_secure: bool = False
    trust_proxy: bool = False

    # Per-scope rate limits (in-memory sliding window, single process)
    login_rate_limit: int = 10
    login_rate_window_seconds: int = 60
    register_rate_limit: int = 25
    register_rate_window_seconds: int = 3600
    forgot_password_rate_limit: int = 5
    forgot_password_rate_window_seconds: int = 3600
    reset_password_rate_limit: int = 5
    reset_password_rate_window_seconds: int = 600
    change_password_rate_limit: int = 5
    change_password_rate_window_seconds: int = 3600
    change_email_rate_limit: int = 5
    change_email_rate_window_seconds: int = 3600
    send_now_rate_limit: int = 2
    send_now_rate_window_seconds: int = 3600

    jwt_secret: str = _DEFAULT_JWT_SECRET
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # CORS — JSON array in env var, e.g. ALLOWED_ORIGINS=["https://app.example.com"]
    allowed_origins: list[str] = ["http://localhost:3010", "http://localhost:3000"]

    # SMTP (optional)
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: SecretStr | None = None
    smtp_use_tls: bool = True
    reminder_from: str | None = None

    # Email domain blocklist — addresses whose domain matches are silently skipped
    # by the reminder/summary scheduler. Set via EMAIL_BLOCKED_DOMAINS as a JSON
    # array, e.g. '["test.com","example.com"]'. Defaults cover E2E test addresses.
    email_blocked_domains: list[str] = ["test.com", "example.com"]

    # Password reset
    app_base_url: str = "http://localhost:3010"
    password_reset_token_expire_minutes: int = 60

    # Restore safety net — how long a pre-restore snapshot stays recoverable
    restore_snapshot_retention_days: int = 7

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @field_validator("password_reset_token_expire_minutes")
    @classmethod
    def warn_if_no_token_expiry(cls, v: int) -> int:
        if v == 0:
            warnings.warn(
                "PASSWORD_RESET_TOKEN_EXPIRE_MINUTES=0: reset tokens never expire. "
                "Only use this in development/testing.",
                stacklevel=2,
            )
        return v

    @field_validator("jwt_secret")
    @classmethod
    def jwt_secret_must_not_be_default(cls, v: str) -> str:
        if v == _DEFAULT_JWT_SECRET:
            if os.getenv("ENVIRONMENT", "development") == "production":
                raise ValueError(
                    "JWT_SECRET is set to the default placeholder. "
                    "Set a strong random value via the JWT_SECRET environment variable."
                )
            warnings.warn(
                "JWT_SECRET is set to the default placeholder — insecure for production.",
                stacklevel=2,
            )
        return v

    @model_validator(mode="after")
    def warn_if_secure_cookie_over_http(self) -> "Settings":
        if not self.cookie_secure:
            return self
        local_hosts = {"localhost", "127.0.0.1", "::1"}
        if (
            self.app_base_url.lower().startswith("http://")
            and urlparse(self.app_base_url).hostname not in local_hosts
        ):
            warnings.warn(
                f"COOKIE_SECURE=true but APP_BASE_URL ({self.app_base_url}) is "
                "plain HTTP. Browsers reject Secure cookies over HTTP, so login "
                "appears to succeed but every request bounces back to /login. "
                "Serve over HTTPS or set COOKIE_SECURE=false.",
                stacklevel=2,
            )
        return self


settings = Settings()
