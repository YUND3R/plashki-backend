import uuid
import hmac

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import decode_access_token_claims
from app.db.models import UserProfile
from app.db.session import get_session

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}


async def get_current_user_id(
    request: Request,
    session: AsyncSession = Depends(get_session),
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
        claims = decode_access_token_claims(token)
    except ValueError:
        raise HTTPException(
            status_code=401,
            detail="Неверный или просроченный токен",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = await session.get(UserProfile, claims.user_id)
    if user is None or user.token_version != claims.token_version:
        raise HTTPException(
            status_code=401,
            detail="Сессия недействительна. Войдите снова.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return claims.user_id
