from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.password import hash_password, validate_password_strength
from app.core.config import settings
from app.db.models import PendingRegistration, UserProfile
from app.services.user_uniqueness import registration_conflict


def _pg_error_text(exc: IntegrityError) -> str:
    o = getattr(exc, "orig", None)
    return str(o) if o else str(exc)


def _integrity_kind(exc: IntegrityError) -> str | None:
    """'username' | 'email' из constraint / текста PostgreSQL."""
    o = getattr(exc, "orig", None)
    cname = (getattr(o, "constraint_name", None) or "").lower()
    if "username" in cname:
        return "username"
    if "email" in cname:
        return "email"

    raw = _pg_error_text(exc).lower()
    if "username" in raw or " (username)" in raw:
        return "username"
    if "email" in raw or " (email)" in raw:
        return "email"
    return None


async def register_user(
    session: AsyncSession,
    *,
    username: str,
    email: str,
    password: str,
    first_name: str,
    last_name: str,
    avatar_url: str | None = None,
) -> tuple[str | None, PendingRegistration | None, str]:
    username = username.strip()
    email = email.strip()
    first_name = first_name.strip()
    last_name = last_name.strip()
    if not username or not email:
        return "empty_fields", None, ""
    if not first_name or not last_name:
        return "empty_names", None, ""
    if len(first_name) > 100 or len(last_name) > 100:
        return "name_too_long", None, ""
    if validate_password_strength(password):
        return "weak_password", None, ""

    conflict = await registration_conflict(session, username, email)
    if conflict == "username":
        return "username", None, ""
    if conflict == "email":
        return "email", None, ""

    # Удаляем только истёкшие/использованные pending. Активную регистрацию сохраняем,
    # чтобы повторный POST не мог обходить лимит отправки verification-писем.
    await session.execute(
        delete(PendingRegistration).where(
            (
                (PendingRegistration.username == username)
                | (func.lower(PendingRegistration.email) == email.lower())
            )
            & (
                (PendingRegistration.consumed_at.is_not(None))
                | (PendingRegistration.expires_at <= datetime.now(UTC))
            )
        )
    )

    pending = PendingRegistration(
        username=username,
        email=email,
        first_name=first_name,
        last_name=last_name,
        avatar_url=avatar_url,
        hashed_password=hash_password(password),
        expires_at=datetime.now(UTC)
        + timedelta(minutes=settings.email_verification_token_ttl_minutes),
    )
    session.add(pending)
    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        kind = _integrity_kind(e)
        pg = _pg_error_text(e)
        if kind == "username":
            return "username", None, pg
        if kind == "email":
            return "email", None, pg
        # Проверяем конфликт с активной pending-регистрацией
        p1 = await session.execute(
            select(PendingRegistration.id)
            .where(
                and_(
                    PendingRegistration.username == username,
                    PendingRegistration.consumed_at.is_(None),
                )
            )
            .limit(1)
        )
        if p1.first() is not None:
            return "username", None, pg
        p2 = await session.execute(
            select(PendingRegistration.id)
            .where(
                and_(
                    func.lower(PendingRegistration.email) == email.lower(),
                    PendingRegistration.consumed_at.is_(None),
                )
            )
            .limit(1)
        )
        if p2.first() is not None:
            return "email", None, pg
        # гонка или неочевидное сообщение — повторная проверка по user_profile
        again = await registration_conflict(session, username, email)
        if again == "username":
            return "username", None, pg
        if again == "email":
            return "email", None, pg
        return "integrity", None, pg
    await session.refresh(pending)
    return None, pending, ""
