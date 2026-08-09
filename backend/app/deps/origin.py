from fastapi import HTTPException, Request

from app.core.config import settings


async def require_trusted_origin(request: Request) -> None:
    """Reject browser requests that could establish a cookie from another origin."""
    if settings.environment == "local":
        return
    origin = (request.headers.get("origin") or "").strip().rstrip("/")
    if not origin or origin not in {value.rstrip("/") for value in settings.cors_origin_list}:
        raise HTTPException(status_code=403, detail="Недопустимый Origin для auth-запроса.")
