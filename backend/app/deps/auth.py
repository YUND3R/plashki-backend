import uuid
import hmac

from fastapi import HTTPException, Request

from app.core.config import settings
from app.core.security import decode_access_token

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}


def get_current_user_id(
    request: Request,
) -> uuid.UUID:
    token = (request.cookies.get(settings.auth_cookie_name) or "").strip()

    if not token:
        raise HTTPException(
            status_code=401,
            detail="Нужна авторизация: cookie с access token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if request.method.upper() not in _SAFE_METHODS:
        cookie_csrf = (request.cookies.get(settings.csrf_cookie_name) or "").strip()
        header_csrf = (request.headers.get(settings.csrf_header_name) or "").strip()
        if (
            not cookie_csrf
            or not header_csrf
            or not hmac.compare_digest(cookie_csrf, header_csrf)
        ):
            raise HTTPException(
                status_code=403,
                detail=(
                    "CSRF проверка не пройдена: передайте корректный "
                    f"{settings.csrf_header_name}."
                ),
            )

    try:
        return decode_access_token(token)
    except ValueError:
        raise HTTPException(
            status_code=401,
            detail="Неверный или просроченный токен",
            headers={"WWW-Authenticate": "Bearer"},
        )
