from fastapi import HTTPException, Request
from urllib.parse import urlparse

from app.core.config import settings


async def require_trusted_origin(request: Request) -> None:
    """Reject browser requests that could establish a cookie from another origin."""
    if settings.environment == "local":
        return
    allowed_origins = {value.rstrip("/") for value in settings.cors_origin_list}
    scheme = request.url.scheme
    host = request.url.netloc
    if host:
        allowed_origins.add(f"{scheme}://{host}")

    origin = (request.headers.get("origin") or "").strip().rstrip("/")
    if origin:
        if origin in allowed_origins:
            return
        raise HTTPException(status_code=403, detail="Недопустимый Origin для auth-запроса.")

    referer = (request.headers.get("referer") or "").strip()
    if referer:
        referer_origin = (
            f"{urlparse(referer).scheme}://{urlparse(referer).netloc}".rstrip("/")
        )
        if referer_origin in allowed_origins:
            return
        raise HTTPException(status_code=403, detail="Недопустимый Referer для auth-запроса.")

    if not request.headers.get("sec-fetch-site"):
        return
    raise HTTPException(status_code=403, detail="Для browser auth-запроса нужен Origin или Referer.")
