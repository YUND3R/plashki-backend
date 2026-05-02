import html
import uuid
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Path,
    Query,
    Request,
    UploadFile,
)
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import create_access_token
from app.db.session import get_session
from app.deps.auth import get_current_user_id
from app.db.models import UserProfile
from app.schemas.auth import (
    ForgotPasswordBody,
    LoginBody,
    MessageResponse,
    PatchMeProfileBody,
    ResetPasswordBody,
    TokenResponse,
    UserMe,
    VerifyEmailBody,
)
from app.services.alerting import alert_service
from app.services import auth_login as auth_login_service
from app.services import email_verification as email_verification_service
from app.services import password_reset as password_reset_service
from app.services import auth_register as auth_register_service
from app.services.password_reset_links import build_password_reset_link
from app.services.email_verification_links import build_email_verification_link
from app.services.photo_storage import remove_stored_file_if_ours, save_image_upload

router = APIRouter(prefix="/auth", tags=["auth"])


def _email_verify_browser_response(
    result: str,
    user: UserProfile | None,
) -> RedirectResponse | HTMLResponse:
    fe = settings.frontend_verify_email_url.strip()

    if result == "ok" and user is not None:
        if fe:
            sep = "&" if "?" in fe else "?"
            return RedirectResponse(
                url=f"{fe}{sep}verified=1",
                status_code=303,
            )
        return HTMLResponse(
            content=(
                "<!DOCTYPE html><html lang=\"ru\"><head><meta charset=\"utf-8\"/>"
                "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"/>"
                "<title>Email подтверждён</title></head><body>"
                "<p>Email подтверждён. Можно закрыть страницу и войти в приложение.</p>"
                "</body></html>"
            ),
            status_code=200,
        )

    if result == "expired_token":
        err_msg = "Ссылка подтверждения просрочена. Запросите письмо снова."
    elif result == "conflict":
        err_msg = "Логин или email уже заняты. Зарегистрируйтесь заново."
    else:
        err_msg = "Неверная или уже использованная ссылка подтверждения."
    if fe:
        sep = "&" if "?" in fe else "?"
        return RedirectResponse(
            url=f"{fe}{sep}verify_error=1",
            status_code=303,
        )
    return HTMLResponse(
        content=(
            "<!DOCTYPE html><html lang=\"ru\"><head><meta charset=\"utf-8\"/>"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"/>"
            "<title>Ошибка</title></head><body>"
            f"<p>{err_msg}</p>"
            "</body></html>"
        ),
        status_code=400,
    )


@router.post(
    "/register",
    response_model=MessageResponse,
    summary="Регистрация (multipart): логин, email, пароль, имя, фамилия; опционально фото",
    description=(
        "Роль всегда USER. Форма **multipart/form-data**: поля username, email, password, "
        "first_name, last_name; опционально файл **avatar** (JPEG, PNG, WebP, GIF). "
        "На email — ссылка с HMAC-подписью (фронт: только hash-фрагмент #vid=&sig=, без утечки в access-log при открытии); "
        "**JWT** — после POST /auth/verify-email или входа."
    ),
)
async def register(
    request: Request,
    username: Annotated[str, Form(min_length=1, max_length=55)],
    email: Annotated[str, Form(min_length=1, max_length=55)],
    password: Annotated[str, Form(min_length=1, max_length=128)],
    first_name: Annotated[str, Form(min_length=1, max_length=100)],
    last_name: Annotated[str, Form(min_length=1, max_length=100)],
    avatar: UploadFile | None = File(None),
    session: AsyncSession = Depends(get_session),
) -> MessageResponse:
    avatar_url: str | None = None
    if avatar is not None and (avatar.filename or "").strip():
        avatar_url = await save_image_upload(avatar, request)

    err, pending, pg_hint = await auth_register_service.register_user(
        session,
        username=username,
        email=email,
        password=password,
        first_name=first_name,
        last_name=last_name,
        avatar_url=avatar_url,
    )
    if err == "empty_fields":
        raise HTTPException(
            status_code=422,
            detail="Логин и email не могут быть пустыми (проверьте пробелы).",
        )
    if err == "empty_names":
        raise HTTPException(
            status_code=422,
            detail="Имя и фамилия не могут быть пустыми (проверьте пробелы).",
        )
    if err == "name_too_long":
        raise HTTPException(
            status_code=422,
            detail="Имя и фамилия — не длиннее 100 символов каждое.",
        )
    if err == "username":
        raise HTTPException(
            status_code=409,
            detail="Пользователь с таким логином уже есть.",
        )
    if err == "email":
        raise HTTPException(
            status_code=409,
            detail="Пользователь с таким email уже есть.",
        )
    if err == "integrity" or pending is None:
        msg = (
            "Не удалось создать пользователя: конфликт в БД "
            "(часто параллельная регистрация). Попробуйте другой логин/email."
        )
        if settings.environment != "production" and pg_hint:
            msg = f"{msg} Технически: {pg_hint[:500]}"
        raise HTTPException(status_code=409, detail=msg)

    token_status, pair = await email_verification_service.create_verification_token_for_pending(
        session, pending_id=pending.id
    )
    if token_status == "ok" and pair:
        tid, sig = pair
        verify_link = build_email_verification_link(
            token_id=tid, signature=sig, request=request
        )
        email_body = (
            "Подтвердите регистрацию в Plashki.\n\n"
            f"Перейдите по ссылке:\n{verify_link}\n\n"
            f"Ссылка действует {settings.email_verification_token_ttl_minutes} минут."
        )
        sent = alert_service.send_email(
            to_email=pending.email,
            subject="Подтверждение email — Plashki",
            body=email_body,
        )
        if not sent:
            alert_service.send_warning(
                "Verification email was not sent",
                f"pending_id={pending.id}, email={pending.email}",
            )
    else:
        alert_service.send_warning(
            "Verification token was not created after register",
            f"pending_id={pending.id}, email={pending.email}, reason={token_status}",
        )

    return MessageResponse(
        message=(
            "Аккаунт создан. Проверьте почту и перейдите по ссылке для подтверждения."
        )
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Вход: логин или email + пароль → JWT",
)
async def login(
    body: LoginBody,
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    user = await auth_login_service.authenticate_by_login_or_email(
        session, body.login, body.password
    )
    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Неверный логин или пароль",
        )
    if user.email_verified_at is None:
        raise HTTPException(
            status_code=403,
            detail=(
                "Сначала подтвердите email — письмо отправлено при регистрации. "
                "Можно запросить повтор: POST /auth/resend-verification."
            ),
        )
    token = create_access_token(user_id=user.id)
    return TokenResponse(access_token=token)


@router.get(
    "/verify-email/{token_id:uuid}/{signature}",
    summary="Подтвердить email (API: id + HMAC в пути)",
    response_model=None,
)
async def verify_email_signed_get(
    token_id: uuid.UUID,
    signature: Annotated[str, Path(min_length=64, max_length=64)],
    session: AsyncSession = Depends(get_session),
) -> RedirectResponse | HTMLResponse:
    result, user = await email_verification_service.verify_email_by_signed_link(
        session, token_id=token_id, signature=signature
    )
    return _email_verify_browser_response(result, user)


@router.get(
    "/verify-email",
    summary="Подтвердить email (устар.: только старые письма ?code= / ?token=)",
    response_model=None,
)
async def verify_email_get(
    code: Annotated[str | None, Query(min_length=8, max_length=512)] = None,
    token: Annotated[str | None, Query(min_length=10, max_length=512)] = None,
    session: AsyncSession = Depends(get_session),
) -> RedirectResponse | HTMLResponse:
    secret = ((code or token) or "").strip()
    if not secret:
        fe = settings.frontend_verify_email_url.strip()
        if fe:
            sep = "&" if "?" in fe else "?"
            return RedirectResponse(url=f"{fe}{sep}verify_error=1", status_code=303)
        return HTMLResponse(
            content=(
                "<!DOCTYPE html><html lang=\"ru\"><head><meta charset=\"utf-8\"/>"
                "<title>Ошибка</title></head><body>"
                "<p>Неверная ссылка.</p>"
                "</body></html>"
            ),
            status_code=422,
        )
    result, user = await email_verification_service.verify_email_by_token(
        session, token=secret
    )
    return _email_verify_browser_response(result, user)


@router.post(
    "/verify-email",
    response_model=TokenResponse,
    summary="Подтвердить email: token_id+signature (или устар. code/token)",
)
async def verify_email(
    body: VerifyEmailBody,
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    if body.token_id is not None and body.signature:
        result, user = await email_verification_service.verify_email_by_signed_link(
            session, token_id=body.token_id, signature=body.signature
        )
    elif body.code:
        result, user = await email_verification_service.verify_email_by_token(
            session, token=body.code
        )
    else:
        raise HTTPException(status_code=422, detail="Нужны token_id и signature или code.")
    if result == "ok" and user is not None:
        return TokenResponse(access_token=create_access_token(user_id=user.id))
    if result == "conflict":
        raise HTTPException(
            status_code=409,
            detail="Логин или email уже заняты. Зарегистрируйтесь снова.",
        )
    if result == "expired_token":
        raise HTTPException(status_code=400, detail="Ссылка подтверждения просрочена.")
    raise HTTPException(status_code=400, detail="Неверный токен подтверждения.")


@router.post(
    "/resend-verification",
    response_model=MessageResponse,
    summary="Повторно отправить письмо подтверждения email",
    description=(
        "Одинаковый ответ при любом email, чтобы не раскрывать наличие аккаунта "
        "(как /auth/forgot-password)."
    ),
)
async def resend_verification(
    request: Request,
    body: ForgotPasswordBody,
    session: AsyncSession = Depends(get_session),
) -> MessageResponse:
    to_email, pair, reason = await email_verification_service.create_verification_token_for_email(
        session, email=body.email
    )
    if to_email is None or pair is None:
        if reason in {"cooldown", "limit"}:
            return MessageResponse(
                message="Если аккаунт существует и email не подтверждён, письмо уже отправлялось. Повторите позже."
            )
        return MessageResponse(
            message="Если аккаунт существует и email не подтверждён, письмо отправлено."
        )

    tid, sig = pair
    verify_link = build_email_verification_link(
        token_id=tid, signature=sig, request=request
    )
    email_body = (
        "Подтвердите регистрацию в Plashki.\n\n"
        f"Перейдите по ссылке:\n{verify_link}\n\n"
        f"Ссылка действует {settings.email_verification_token_ttl_minutes} минут."
    )

    sent = alert_service.send_email(
        to_email=to_email,
        subject="Подтверждение email — Plashki",
        body=email_body,
    )
    if not sent:
        alert_service.send_warning(
            "Verification email was not sent (resend)",
            f"email={to_email}",
        )
    return MessageResponse(
        message="Если аккаунт существует и email не подтверждён, письмо отправлено."
    )


@router.post(
    "/forgot-password",
    response_model=MessageResponse,
    summary="Запрос на сброс пароля",
    description="Всегда возвращает одинаковый ответ, чтобы не раскрывать наличие email в системе.",
)
async def forgot_password(
    request: Request,
    body: ForgotPasswordBody,
    session: AsyncSession = Depends(get_session),
) -> MessageResponse:
    user, pair = await password_reset_service.create_reset_token_for_email(
        session, email=body.email
    )
    if user is None or pair is None:
        return MessageResponse(message="Если аккаунт существует, письмо уже отправлено.")

    rid, sig = pair
    reset_link = build_password_reset_link(token_id=rid, signature=sig, request=request)
    email_body = (
        "Вы запросили сброс пароля.\n\n"
        f"Перейдите по ссылке:\n{reset_link}\n\n"
        f"Ссылка действует {settings.reset_token_ttl_minutes} минут."
    )

    sent = alert_service.send_email(
        to_email=user.email,
        subject="Сброс пароля Plashki",
        body=email_body,
    )
    if not sent:
        alert_service.send_warning(
            "Password reset email was not sent",
            f"user_id={user.id}, email={user.email}",
        )
    return MessageResponse(message="Если аккаунт существует, письмо уже отправлено.")


@router.post(
    "/reset-password",
    response_model=MessageResponse,
    summary="Сброс пароля: token_id+signature или устаревший token",
)
async def reset_password(
    body: ResetPasswordBody,
    session: AsyncSession = Depends(get_session),
) -> MessageResponse:
    if body.token_id is not None and body.signature:
        result = await password_reset_service.reset_password_by_signed(
            session,
            token_id=body.token_id,
            signature=body.signature,
            new_password=body.new_password,
        )
    elif body.token:
        result = await password_reset_service.reset_password_by_token(
            session,
            token=body.token,
            new_password=body.new_password,
        )
    else:
        raise HTTPException(status_code=422, detail="Нужны token_id и signature или token.")
    if result == "ok":
        return MessageResponse(message="Пароль успешно обновлен.")
    if result == "expired_token":
        raise HTTPException(status_code=400, detail="Токен сброса просрочен.")
    raise HTTPException(status_code=400, detail="Неверный токен сброса.")


@router.api_route(
    "/reset-password-form",
    methods=["GET", "HEAD"],
    response_class=HTMLResponse,
    summary="Страница формы сброса (без фронта)",
    include_in_schema=False,
)
async def reset_password_form_get(
    rid: uuid.UUID = Query(description="Идентификатор из письма"),
    sig: str = Query(min_length=64, max_length=64),
):
    esc_id = html.escape(str(rid))
    esc_sig = html.escape(sig)
    page = f"""<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Сброс пароля</title></head><body>
<p>Введите новый пароль.</p>
<form method="post" action="/auth/reset-password-form">
<input type="hidden" name="token_id" value="{esc_id}"/>
<input type="hidden" name="signature" value="{esc_sig}"/>
<p><label>Новый пароль (мин. 8 симв.): <input type="password" name="new_password" minlength="8" required /></label></p>
<p><button type="submit">Сохранить</button></p>
</form></body></html>"""
    return HTMLResponse(content=page, status_code=200)


@router.post(
    "/reset-password-form",
    response_model=MessageResponse,
    summary="Отправка формы сброса",
    include_in_schema=False,
)
async def reset_password_form_post(
    token_id: uuid.UUID = Form(),
    signature: str = Form(min_length=64, max_length=64),
    new_password: str = Form(min_length=8, max_length=128),
    session: AsyncSession = Depends(get_session),
) -> MessageResponse:
    result = await password_reset_service.reset_password_by_signed(
        session,
        token_id=token_id,
        signature=signature,
        new_password=new_password,
    )
    if result == "ok":
        return MessageResponse(message="Пароль успешно обновлен. Можно войти.")
    if result == "expired_token":
        raise HTTPException(status_code=400, detail="Ссылка сброса просрочена.")
    raise HTTPException(status_code=400, detail="Неверная ссылка сброса.")


@router.get(
    "/me",
    response_model=UserMe,
    summary="Текущий пользователь по JWT",
)
async def me(
    session: AsyncSession = Depends(get_session),
    user_id: uuid.UUID = Depends(get_current_user_id),
) -> UserMe:
    user = await session.get(UserProfile, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Пользователь не найден")
    return UserMe.model_validate(user)


@router.patch(
    "/me",
    response_model=UserMe,
    summary="Сменить имя и фамилию (только свой аккаунт, Bearer JWT)",
    description="JSON: **first_name**, **last_name**. Пустые строки после trim недопустимы.",
)
async def patch_me_profile(
    body: PatchMeProfileBody,
    session: AsyncSession = Depends(get_session),
    user_id: uuid.UUID = Depends(get_current_user_id),
) -> UserMe:
    user = await session.get(UserProfile, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Пользователь не найден")

    fn = body.first_name.strip()
    ln = body.last_name.strip()
    if not fn or not ln:
        raise HTTPException(
            status_code=422,
            detail="Имя и фамилия не могут быть пустыми (проверьте пробелы).",
        )
    if len(fn) > 100 or len(ln) > 100:
        raise HTTPException(
            status_code=422,
            detail="Имя и фамилия — не длиннее 100 символов каждое.",
        )

    user.first_name = fn
    user.last_name = ln
    await session.commit()
    await session.refresh(user)
    return UserMe.model_validate(user)


@router.patch(
    "/me/avatar",
    response_model=UserMe,
    summary="Загрузить или заменить фото профиля (одно, Bearer JWT)",
    description=(
        "multipart/form-data, поле **avatar** — одно изображение (JPEG, PNG, WebP, GIF). "
        "Старое фото, если было загружено через этот же сервис, удаляется с диска."
    ),
)
async def patch_me_avatar(
    request: Request,
    avatar: UploadFile = File(..., description="Новое фото профиля"),
    session: AsyncSession = Depends(get_session),
    user_id: uuid.UUID = Depends(get_current_user_id),
) -> UserMe:
    user = await session.get(UserProfile, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Пользователь не найден")

    previous = user.avatar_url
    new_url = await save_image_upload(avatar, request)
    if len(new_url) > 1024:
        raise HTTPException(status_code=400, detail="Внутренняя ошибка: URL аватара слишком длинный")

    user.avatar_url = new_url
    await session.commit()
    await session.refresh(user)

    remove_stored_file_if_ours(previous)

    return UserMe.model_validate(user)


@router.delete(
    "/me/avatar",
    response_model=UserMe,
    summary="Удалить фото профиля (Bearer JWT)",
    description="Сбрасывает avatar_url в null. Если файл был загружен через этот сервис, он удаляется с диска.",
)
async def delete_me_avatar(
    session: AsyncSession = Depends(get_session),
    user_id: uuid.UUID = Depends(get_current_user_id),
) -> UserMe:
    user = await session.get(UserProfile, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Пользователь не найден")

    previous = user.avatar_url
    user.avatar_url = None
    await session.commit()
    await session.refresh(user)

    remove_stored_file_if_ours(previous)

    return UserMe.model_validate(user)
