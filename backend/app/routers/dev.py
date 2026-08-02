import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.password import hash_password
from app.db.base import Role, Subscription
from app.db.models import UserProfile
from app.db.session import get_session
from app.notifications.email_templates import (
    build_password_reset_email_html,
    build_registration_verification_email_html,
    resolve_email_assets_base_url,
)
from app.services.user_uniqueness import registration_conflict
from app.schemas.dev_user import (
    TestAdminCreateBody,
    TestUserCreateBody,
    TestUserOut,
)

router = APIRouter(prefix="/dev", tags=["dev"])


@router.post(
    "/test-user",
    response_model=TestUserOut,
    summary="[ТЕСТ] Создать пользователя",
)
async def dev_create_test_user(
    body: TestUserCreateBody,
    session: AsyncSession = Depends(get_session),
) -> TestUserOut:
    conflict = await registration_conflict(session, body.username, body.email)
    if conflict == "username":
        raise HTTPException(
            status_code=409,
            detail="Логин (username) уже занят другим аккаунтом.",
        )
    if conflict == "email":
        raise HTTPException(
            status_code=409,
            detail="Этот email уже зарегистрирован. Игровой nickname здесь не проверяется.",
        )
    user = UserProfile(
        username=body.username,
        email=body.email,
        first_name="",
        last_name="",
        nickname=body.username[:255],
        hashed_password=hash_password(body.password),
        role=body.role,
        subscription=Subscription.FREE,
        email_verified_at=datetime.now(timezone.utc),
    )
    session.add(user)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail="Конфликт уникальности при сохранении (возможен параллельный запрос). Проверьте username и email.",
        )
    await session.refresh(user)
    return TestUserOut.model_validate(user)


@router.post(
    "/test-admin",
    response_model=TestUserOut,
    summary="[ТЕСТ] Создать администратора",
)
async def dev_create_test_admin(
    body: TestAdminCreateBody,
    session: AsyncSession = Depends(get_session),
) -> TestUserOut:
    conflict = await registration_conflict(session, body.username, body.email)
    if conflict == "username":
        raise HTTPException(
            status_code=409,
            detail="Логин (username) уже занят — поменяй username в теле запроса.",
        )
    if conflict == "email":
        raise HTTPException(
            status_code=409,
            detail="Этот email уже зарегистрирован — поменяй email в теле запроса.",
        )
    user = UserProfile(
        username=body.username,
        email=body.email,
        first_name="",
        last_name="",
        nickname=body.username[:255],
        hashed_password=hash_password(body.password),
        role=Role.ADMIN,
        subscription=Subscription.FREE,
        email_verified_at=datetime.now(timezone.utc),
    )
    session.add(user)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail="Конфликт уникальности при сохранении (возможен параллельный запрос). Проверьте username и email.",
        )
    await session.refresh(user)
    return TestUserOut.model_validate(user)


@router.get(
    "/email-preview/password-reset",
    response_class=HTMLResponse,
    summary="[ТЕСТ] Превью HTML-письма сброса пароля",
)
async def dev_preview_password_reset_email() -> HTMLResponse:
    assets_base = resolve_email_assets_base_url()
    html = build_password_reset_email_html(
        username="demo",
        action_url=f"{settings.frontend_reset_password_url or 'https://plash-ki.ru/reset-password'}#rid=1&sig=preview",
        ttl_minutes=settings.reset_token_ttl_minutes,
        assets_base_url=assets_base,
    )
    return HTMLResponse(content=html)


@router.get(
    "/email-preview/registration",
    response_class=HTMLResponse,
    summary="[ТЕСТ] Превью HTML-письма регистрации",
)
async def dev_preview_registration_email() -> HTMLResponse:
    assets_base = resolve_email_assets_base_url()
    html = build_registration_verification_email_html(
        username="demo",
        action_url=f"{settings.frontend_verify_email_url or 'https://plash-ki.ru/verify-email'}#vid=1&sig=preview",
        ttl_minutes=settings.email_verification_token_ttl_minutes,
        assets_base_url=assets_base,
    )
    return HTMLResponse(content=html)


@router.get(
    "/users/{user_id}",
    response_model=TestUserOut,
    summary="[ТЕСТ] Профиль и роль пользователя",
)
async def dev_get_user(
    user_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> TestUserOut:
    user = await session.get(UserProfile, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return TestUserOut.model_validate(user)
