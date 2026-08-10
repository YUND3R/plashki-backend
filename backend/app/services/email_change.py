import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.link_signing import sign_email_change, verify_email_change_hmac
from app.core.password import verify_password
from app.db.models import EmailChangeToken, UserProfile

async def start_email_change(
    session: AsyncSession, *, user_id: uuid.UUID, new_email: str, current_password: str
) -> tuple[str, tuple[uuid.UUID, str] | None, str | None]:
    user = await session.get(UserProfile, user_id)
    if user is None or not verify_password(current_password, user.hashed_password):
        return "invalid_credentials", None, None
    normalized = new_email.strip().lower()
    if not normalized or normalized == user.email.lower():
        return "invalid_email", None, None
    exists = await session.execute(
        select(UserProfile.id).where(func.lower(UserProfile.email) == normalized).limit(1)
    )
    if exists.first() is not None:
        return "unavailable", None, None

    now = datetime.now(UTC)
    await session.execute(
        update(EmailChangeToken)
        .where(and_(EmailChangeToken.user_id == user.id, EmailChangeToken.used_at.is_(None)))
        .values(used_at=now)
    )
    row = EmailChangeToken(
        user_id=user.id,
        new_email=normalized,
        expires_at=now + timedelta(minutes=settings.email_change_token_ttl_minutes),
    )
    session.add(row)
    await session.flush()
    signature = sign_email_change(row.id, user.id, row.expires_at)
    await session.commit()
    return "ok", (row.id, signature), user.email


async def confirm_email_change(
    session: AsyncSession, *, token_id: uuid.UUID, signature: str
) -> tuple[str, UserProfile | None]:
    row = await session.get(EmailChangeToken, token_id)
    now = datetime.now(UTC)
    if row is None or row.used_at is not None or row.expires_at <= now:
        return "invalid_token", None
    if not verify_email_change_hmac(row.id, row.user_id, row.expires_at, signature):
        return "invalid_token", None
    user = await session.get(UserProfile, row.user_id)
    if user is None:
        return "invalid_token", None
    exists = await session.execute(
        select(UserProfile.id).where(
            func.lower(UserProfile.email) == row.new_email.lower(),
            UserProfile.id != user.id,
        ).limit(1)
    )
    if exists.first() is not None:
        return "unavailable", None
    user.email = row.new_email
    user.email_verified_at = now
    user.token_version += 1
    row.used_at = now
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        return "unavailable", None
    await session.refresh(user)
    return "ok", user
