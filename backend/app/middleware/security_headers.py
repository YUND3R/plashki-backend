from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Снижает утечку секретов через Referer; запрещает кэш для чувствительных auth-ответов."""

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        path = request.url.path
        if path.startswith("/auth/verify-email") or path.startswith("/auth/reset-password"):
            response.headers.setdefault("Referrer-Policy", "no-referrer")
            response.headers.setdefault("Cache-Control", "no-store, private")
        return response
