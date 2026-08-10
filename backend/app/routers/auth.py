import html
import secrets
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
    Response,
    UploadFile,
)
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import create_access_token
from app.db.session import get_session
from app.deps.auth import get_current_user_id
from app.deps.origin import require_trusted_origin
from app.db.models import UserProfile
from app.notifications.email_templates import (
    build_password_reset_email_html,
    build_password_reset_email_plain,
    build_registration_verification_email_html,
    build_registration_verification_email_plain,
    email_inline_images,
    resolve_email_assets_base_url,
)
from app.notifications.providers import get_notification_facade
from app.schemas.auth import (
    AuthSessionResponse,
    ChangeEmailConfirmBody,
    ChangeEmailRequestBody,
    ForgotPasswordBody,
    LoginBody,
    MessageResponse,
    PatchMeProfileBody,
    ResetPasswordBody,
    UserMe,
    VerifyEmailBody,
)
from app.services import auth_login as auth_login_service
from app.services import email_verification as email_verification_service
from app.services import password_reset as password_reset_service
from app.services import auth_register as auth_register_service
from app.services import email_change as email_change_service
from app.services.password_reset_links import build_password_reset_link
from app.services.email_verification_links import build_email_verification_link
from app.services.photo_storage import remove_stored_file_if_ours, save_image_upload

router = APIRouter(prefix="/auth", tags=["auth"])
alert_service = get_notification_facade()


def _auth_cookie_domain() -> str | None:
    domain = settings.auth_cookie_domain.strip()
    return domain or None


def _set_access_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=token,
        max_age=settings.access_token_expire_minutes * 60,
        httponly=True,
        secure=settings.auth_cookie_secure_effective,
        samesite=settings.auth_cookie_samesite,
        path="/",
        domain=_auth_cookie_domain(),
    )


def _new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def _set_csrf_cookie(response: Response, csrf_token: str) -> None:
    response.set_cookie(
        key=settings.csrf_cookie_name,
        value=csrf_token,
        max_age=settings.access_token_expire_minutes * 60,
        httponly=False,
        secure=settings.auth_cookie_secure_effective,
        samesite=settings.auth_cookie_samesite,
        path="/",
        domain=_auth_cookie_domain(),
    )


def _csrf_from_request(request: Request) -> str | None:
    value = (request.cookies.get(settings.csrf_cookie_name) or "").strip()
    return value or None


def _user_me_response(request: Request, user: UserProfile) -> UserMe:
    return UserMe.model_validate(user).model_copy(
        update={"csrf_token": _csrf_from_request(request)}
    )


def _issue_auth_session(
    response: Response,
    user: UserProfile,
    *,
    message: str = "Вы успешно вошли в аккаунт.",
) -> AuthSessionResponse:
    token = create_access_token(user_id=user.id, token_version=user.token_version)
    csrf_token = _new_csrf_token()
    _set_access_cookie(response, token)
    _set_csrf_cookie(response, csrf_token)
    return AuthSessionResponse(message=message, csrf_token=csrf_token)


def _clear_access_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.auth_cookie_name,
        path="/",
        domain=_auth_cookie_domain(),
        secure=settings.auth_cookie_secure_effective,
        httponly=True,
        samesite=settings.auth_cookie_samesite,
    )


def _clear_csrf_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.csrf_cookie_name,
        path="/",
        domain=_auth_cookie_domain(),
        secure=settings.auth_cookie_secure_effective,
        httponly=False,
        samesite=settings.auth_cookie_samesite,
    )


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
        "сессия ставится cookie после POST /auth/verify-email или входа."
    ),
)
async def register(
    request: Request,
    username: Annotated[str, Form(min_length=1, max_length=55)],
    email: Annotated[str, Form(min_length=1, max_length=55)],
    password: Annotated[str, Form(min_length=8, max_length=128)],
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
    if err == "weak_password":
        raise HTTPException(status_code=422, detail="Пароль должен содержать минимум 8 символов.")
    if err == "username":
        raise HTTPException(
            status_code=409,
            detail="Логин или email уже заняты.",
        )
    if err == "email":
        raise HTTPException(
            status_code=409,
            detail="Логин или email уже заняты.",
        )
    if err == "integrity" or pending is None:
        msg = (
            "Не удалось создать пользователя: конфликт в БД "
            "(часто параллельная регистрация). Попробуйте другой логин/email."
        )
        if settings.environment == "local" and pg_hint:
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
        assets_base = resolve_email_assets_base_url(
            request_base_url=str(request.base_url),
        )
        email_body = build_registration_verification_email_plain(
            username=pending.username,
            action_url=verify_link,
            ttl_minutes=settings.email_verification_token_ttl_minutes,
        )
        email_html = build_registration_verification_email_html(
            username=pending.username,
            action_url=verify_link,
            ttl_minutes=settings.email_verification_token_ttl_minutes,
            assets_base_url=assets_base,
        )
        sent = alert_service.send_email(
            to_email=pending.email,
            subject="Подтверждение email — Plashki",
            body=email_body,
            html_body=email_html,
            inline_images=email_inline_images(assets_base_url=assets_base),
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
    response_model=AuthSessionResponse,
    summary="Вход: логин или email + пароль → сессия в HttpOnly cookie",
)
async def login(
    body: LoginBody,
    response: Response,
    session: AsyncSession = Depends(get_session),
    _origin: None = Depends(require_trusted_origin),
) -> AuthSessionResponse:
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
            status_code=401,
            detail="Неверный логин или пароль",
        )
    return _issue_auth_session(response, user)


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
    vid: uuid.UUID | None = None,
    sig: Annotated[str | None, Query(min_length=64, max_length=64)] = None,
    session: AsyncSession = Depends(get_session),
) -> RedirectResponse | HTMLResponse:
    if vid is not None and sig:
        result, user = await email_verification_service.verify_email_by_signed_link(
            session, token_id=vid, signature=sig
        )
        return _email_verify_browser_response(result, user)
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
    response_model=AuthSessionResponse,
    summary="Подтвердить email и открыть сессию в cookie",
)
async def verify_email(
    body: VerifyEmailBody,
    response: Response,
    session: AsyncSession = Depends(get_session),
    _origin: None = Depends(require_trusted_origin),
) -> AuthSessionResponse:
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
        return _issue_auth_session(
            response,
            user,
            message="Email подтверждён. Вы вошли в аккаунт.",
        )
    if result == "conflict":
        raise HTTPException(
            status_code=409,
            detail="Логин или email уже заняты. Зарегистрируйтесь снова.",
        )
    if result == "expired_token":
        raise HTTPException(status_code=400, detail="Ссылка подтверждения просрочена.")
    raise HTTPException(status_code=400, detail="Неверный токен подтверждения.")


@router.post(
    "/logout",
    response_model=MessageResponse,
    summary="Выход: очистить auth cookie",
)
async def logout(
    response: Response,
    session: AsyncSession = Depends(get_session),
    user_id: uuid.UUID = Depends(get_current_user_id),
) -> MessageResponse:
    user = await session.get(UserProfile, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Пользователь не найден")
    user.token_version += 1
    await session.commit()
    _clear_access_cookie(response)
    _clear_csrf_cookie(response)
    return MessageResponse(message="Вы успешно вышли из аккаунта.")


@router.post("/change-email/request", response_model=MessageResponse)
async def request_email_change(
    body: ChangeEmailRequestBody,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user_id: uuid.UUID = Depends(get_current_user_id),
) -> MessageResponse:
    status, pair, old_email = await email_change_service.start_email_change(
        session,
        user_id=user_id,
        new_email=body.new_email,
        current_password=body.current_password,
    )
    if status == "invalid_credentials":
        raise HTTPException(status_code=403, detail="Не удалось подтвердить смену email.")
    if status in {"invalid_email", "unavailable"} or pair is None:
        return MessageResponse(message="Если адрес доступен, письмо с подтверждением отправлено.")

    token_id, signature = pair
    frontend = settings.frontend_verify_email_url.strip().rstrip("/")
    if not frontend:
        raise HTTPException(status_code=503, detail="Смена email временно недоступна.")
    confirm_url = f"{frontend}#change_email_token={token_id}&sig={signature}"
    sent = alert_service.send_email(
        to_email=body.new_email.strip().lower(),
        subject="Подтверждение нового email — Plashki",
        body=f"Подтвердите новый email: {confirm_url}",
    )
    if old_email:
        alert_service.send_email(
            to_email=old_email,
            subject="Запрос на смену email — Plashki",
            body="Для вашего аккаунта запрошена смена email. Если это были не вы, смените пароль.",
        )
    if not sent:
        alert_service.send_warning("Email change confirmation was not sent", f"user_id={user_id}")
    return MessageResponse(message="Если адрес доступен, письмо с подтверждением отправлено.")


@router.post("/change-email/confirm", response_model=MessageResponse)
async def confirm_email_change(
    body: ChangeEmailConfirmBody,
    session: AsyncSession = Depends(get_session),
    _origin: None = Depends(require_trusted_origin),
) -> MessageResponse:
    status, _user = await email_change_service.confirm_email_change(
        session, token_id=body.token_id, signature=body.signature
    )
    if status != "ok":
        raise HTTPException(status_code=400, detail="Неверная, просроченная или недоступная ссылка.")
    return MessageResponse(message="Email изменён. Войдите в аккаунт снова.")


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
    to_email, pair, _reason, username = await email_verification_service.create_verification_token_for_email(
        session, email=body.email
    )
    if to_email is None or pair is None:
        return MessageResponse(
            message="Если аккаунт существует и email не подтверждён, письмо отправлено."
        )

    tid, sig = pair
    verify_link = build_email_verification_link(
        token_id=tid, signature=sig, request=request
    )
    assets_base = resolve_email_assets_base_url(
        request_base_url=str(request.base_url),
    )
    display_name = username or to_email.split("@", 1)[0]
    email_body = build_registration_verification_email_plain(
        username=display_name,
        action_url=verify_link,
        ttl_minutes=settings.email_verification_token_ttl_minutes,
    )
    email_html = build_registration_verification_email_html(
        username=display_name,
        action_url=verify_link,
        ttl_minutes=settings.email_verification_token_ttl_minutes,
        assets_base_url=assets_base,
    )

    sent = alert_service.send_email(
        to_email=to_email,
        subject="Подтверждение email — Plashki",
        body=email_body,
        html_body=email_html,
        inline_images=email_inline_images(assets_base_url=assets_base),
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
    assets_base = resolve_email_assets_base_url(
        request_base_url=str(request.base_url),
    )
    email_body = build_password_reset_email_plain(
        username=user.username,
        action_url=reset_link,
        ttl_minutes=settings.reset_token_ttl_minutes,
    )
    email_html = build_password_reset_email_html(
        username=user.username,
        action_url=reset_link,
        ttl_minutes=settings.reset_token_ttl_minutes,
        assets_base_url=assets_base,
    )

    sent = alert_service.send_email(
        to_email=user.email,
        subject="Сброс пароля Plashki",
        body=email_body,
        html_body=email_html,
        inline_images=email_inline_images(assets_base_url=assets_base),
    )
    if not sent:
        alert_service.send_warning(
            "Password reset email was not sent",
            f"user_id={user.id}, email={user.email}",
        )
    return MessageResponse(message="Если аккаунт существует, письмо уже отправлено.")


@router.post(
    "/reset-password",
    response_model=AuthSessionResponse,
    summary="Сброс пароля: token_id+signature или устаревший token",
    description="После успешного сброса пароля выдаёт новую сессию в HttpOnly cookie.",
)
async def reset_password(
    body: ResetPasswordBody,
    response: Response,
    session: AsyncSession = Depends(get_session),
    _origin: None = Depends(require_trusted_origin),
) -> AuthSessionResponse:
    user = None
    if body.token_id is not None and body.signature:
        result, user = await password_reset_service.reset_password_by_signed(
            session,
            token_id=body.token_id,
            signature=body.signature,
            new_password=body.new_password,
        )
    elif body.token:
        result, user = await password_reset_service.reset_password_by_token(
            session,
            token=body.token,
            new_password=body.new_password,
        )
    else:
        raise HTTPException(status_code=422, detail="Нужны token_id и signature или token.")
    if result == "ok" and user is not None:
        return _issue_auth_session(
            response,
            user,
            message="Пароль обновлён. Вы вошли в аккаунт.",
        )
    if result == "expired_token":
        raise HTTPException(status_code=400, detail="Токен сброса просрочен.")
    if result == "weak_password":
        raise HTTPException(status_code=422, detail="Пароль должен содержать минимум 8 символов.")
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
    response_model=AuthSessionResponse,
    summary="Отправка формы сброса",
    include_in_schema=False,
)
async def reset_password_form_post(
    response: Response,
    token_id: uuid.UUID = Form(),
    signature: str = Form(min_length=64, max_length=64),
    new_password: str = Form(min_length=8, max_length=128),
    session: AsyncSession = Depends(get_session),
    _origin: None = Depends(require_trusted_origin),
) -> AuthSessionResponse:
    result, user = await password_reset_service.reset_password_by_signed(
        session,
        token_id=token_id,
        signature=signature,
        new_password=new_password,
    )
    if result == "ok" and user is not None:
        return _issue_auth_session(
            response,
            user,
            message="Пароль обновлён. Вы вошли в аккаунт.",
        )
    if result == "expired_token":
        raise HTTPException(status_code=400, detail="Ссылка сброса просрочена.")
    if result == "weak_password":
        raise HTTPException(status_code=422, detail="Пароль должен содержать минимум 8 символов.")
    raise HTTPException(status_code=400, detail="Неверная ссылка сброса.")


@router.get(
    "/me",
    response_model=UserMe,
    summary="Текущий пользователь по JWT",
)
async def me(
    request: Request,
    session: AsyncSession = Depends(get_session),
    user_id: uuid.UUID = Depends(get_current_user_id),
) -> UserMe:
    user = await session.get(UserProfile, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Пользователь не найден")
    return _user_me_response(request, user)


@router.patch(
    "/me",
    response_model=UserMe,
    summary="Сменить имя и фамилию (только свой аккаунт, Bearer JWT)",
    description="JSON: **first_name**, **last_name**. Пустые строки после trim недопустимы.",
)
async def patch_me_profile(
    request: Request,
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
    return _user_me_response(request, user)


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

    return _user_me_response(request, user)


@router.delete(
    "/me/avatar",
    response_model=UserMe,
    summary="Удалить фото профиля (Bearer JWT)",
    description="Сбрасывает avatar_url в null. Если файл был загружен через этот сервис, он удаляется с диска.",
)
async def delete_me_avatar(
    request: Request,
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

    return _user_me_response(request, user)
