from collections import defaultdict, deque
from time import monotonic

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.config import settings

_LIMITS: dict[tuple[str, str], tuple[int, float]] = {
    ("POST", "/auth/login"): (10, 15 * 60),
    ("POST", "/auth/forgot-password"): (5, 60 * 60),
    ("POST", "/auth/register"): (5, 60 * 60),
    ("POST", "/auth/resend-verification"): (5, 60 * 60),
    ("POST", "/auth/change-email/request"): (5, 60 * 60),
    ("POST", "/images/nanobanana/process"): (20, 60 * 60),
}


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Small in-process abuse guard; production replicas should also use nginx limits."""

    def __init__(self, app):
        super().__init__(app)
        self._requests: dict[tuple[str, str, str], deque[float]] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next):
        if settings.environment == "production":
            return await call_next(request)
        limit = _LIMITS.get((request.method, request.url.path))
        if limit is None:
            return await call_next(request)
        max_requests, window_seconds = limit
        client_ip = request.client.host if request.client else "unknown"
        key = (request.method, request.url.path, client_ip)
        now = monotonic()
        timestamps = self._requests[key]
        while timestamps and timestamps[0] <= now - window_seconds:
            timestamps.popleft()
        if len(timestamps) >= max_requests:
            return JSONResponse(
                status_code=429,
                content={"detail": "Слишком много запросов. Повторите позже."},
                headers={"Retry-After": str(int(window_seconds))},
            )
        timestamps.append(now)
        return await call_next(request)
