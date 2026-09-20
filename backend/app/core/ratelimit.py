import time
from collections import defaultdict, deque
from collections.abc import Callable

from fastapi import Depends, HTTPException, Request, status

from app.core.config import settings
from app.core.deps import current_user
from app.models.user import User

# In-memory sliding-window rate limiter. Single uvicorn process only;
# limits are read from `settings` at REQUEST time so tests can tune them.
_WINDOWS: dict[tuple[str, str], deque[float]] = defaultdict(deque)


def _is_allowed(scope: str, key: str, limit: int, window_seconds: int) -> bool:
    now = time.monotonic()
    window = _WINDOWS[(scope, key)]
    while window and window[0] <= now - window_seconds:
        window.popleft()
    if len(window) < limit:
        window.append(now)
        return True
    return False


def reset_rate_limits(scope: str | None = None) -> None:
    """Clear one scope's buckets, or all buckets when scope is None (test helper)."""
    if scope is None:
        _WINDOWS.clear()
        return
    for key in list(_WINDOWS.keys()):
        if key[0] == scope:
            del _WINDOWS[key]


def client_ip(request: Request) -> str:
    if settings.trust_proxy:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def rate_limited(scope: str) -> Callable[..., None]:
    def dependency(request: Request) -> None:
        limit = getattr(settings, f"{scope}_rate_limit")
        window_seconds = getattr(settings, f"{scope}_rate_window_seconds")
        if not _is_allowed(scope, client_ip(request), limit, window_seconds):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests",
            )

    return dependency


def rate_limited_by_user(scope: str) -> Callable[..., None]:
    def dependency(user: User = Depends(current_user)) -> None:
        limit = getattr(settings, f"{scope}_rate_limit")
        window_seconds = getattr(settings, f"{scope}_rate_window_seconds")
        if not _is_allowed(scope, f"user:{user.id}", limit, window_seconds):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests",
            )

    return dependency
