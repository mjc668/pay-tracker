from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decode_token
from app.models.user import User

# auto_error=False so we can fall through to cookie auth when header is absent.
bearer = HTTPBearer(auto_error=False)


def current_user(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    # Accept token from Authorization header OR HttpOnly cookie.
    token: str | None = None
    if creds is not None:
        token = creds.credentials
    else:
        token = request.cookies.get("access_token")

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
        )
    try:
        payload = decode_token(token)
    except JWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")
    try:
        user_id = int(payload["sub"])
        token_version = int(payload.get("tv", 0))
    except (TypeError, ValueError, KeyError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")
    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found"
        )
    if token_version != user.token_version:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Session revoked; please log in again"
        )
    return user


def optional_current_user(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User | None:
    """Like current_user, but returns None instead of raising on any failure.

    Used for endpoints that must still work when the token has expired, been
    revoked, or fails the issuer/audience checks (e.g. logout, which clears
    the HttpOnly cookie a dead token has made otherwise unmatchable).
    """
    token: str | None = None
    if creds is not None:
        token = creds.credentials
    else:
        token = request.cookies.get("access_token")

    if not token:
        return None
    try:
        payload = decode_token(token)
    except JWTError:
        return None
    try:
        user_id = int(payload["sub"])
        token_version = int(payload.get("tv", 0))
    except (TypeError, ValueError, KeyError):
        return None
    user = db.get(User, user_id)
    if not user or not user.is_active or token_version != user.token_version:
        return None
    return user
