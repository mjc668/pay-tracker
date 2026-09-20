import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import jwt

from app.core.config import settings

_JWT_ISSUER = "pay-tracker-backend"
_JWT_AUDIENCE = "pay-tracker"

_COMMON_PASSWORDS: frozenset[str] = frozenset(
    {
        "password",
        "password1",
        "password123",
        "12345678",
        "123456789",
        "1234567890",
        "qwerty",
        "qwerty123",
        "abc12345",
        "abcdefgh",
        "iloveyou",
        "welcome",
        "letmein",
        "monkey",
        "dragon",
        "sunshine",
        "princess",
        "football",
        "baseball",
        "superman",
        "trustno1",
        "whatever",
        "changeme",
        "default",
        "11111111",
        "111111111",
        "00000000",
        "zaq12wsx",
        "passw0rd",
        "admin123",
        "letmein1",
        "qwerty1234",
        "asdfghjk",
        "zxcvbnm",
        "master123",
    }
)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def validate_password_strength(password: str) -> None:
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters")
    if password.lower() in _COMMON_PASSWORDS:
        raise ValueError("Password is too common; pick something less predictable")


def create_access_token(subject: str, *, token_version: int = 0) -> str:
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "sub": subject,
        "tv": token_version,
        "iss": _JWT_ISSUER,
        "aud": _JWT_AUDIENCE,
        "jti": uuid.uuid4().hex,
        "iat": now,
        "exp": expire,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    payload = jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
        audience=_JWT_AUDIENCE,
        issuer=_JWT_ISSUER,
    )
    return payload
