import hashlib
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.link_signing import sign_password_reset, verify_password_reset_hmac
from app.core.password import hash_password, validate_password_strength
from app.db.models import PasswordResetToken, UserProfile


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _expires_at() -> datetime:
    return datetime.now(UTC) + timedelta(minutes=settings.reset_token_ttl_minutes)


async def create_reset_token_for_email(
    session: AsyncSession,
    *,
    email: str,
) -> tuple[UserProfile | None, tuple[uuid.UUID, str] | None]:
    result = await session.execute(
        select(UserProfile).where(func.lower(UserProfile.email) == _normalize_email(email))
    )
    user = result.scalars().first()
    if user is None:
        return None, None

    await session.execute(
        update(PasswordResetToken)
        .where(
            and_(
                PasswordResetToken.user_id == user.id,
                PasswordResetToken.used_at.is_(None),
            )
        )
        .values(used_at=datetime.now(UTC))
    )

    row = PasswordResetToken(
        user_id=user.id,
        token_hash=None,
        expires_at=_expires_at(),
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)
    sig = sign_password_reset(row.id, row.user_id, row.expires_at)
    await session.commit()
    return user, (row.id, sig)


async def reset_password_by_signed(
    session: AsyncSession,
    *,
    token_id: uuid.UUID,
    signature: str,
    new_password: str,
) -> tuple[str, UserProfile | None]:
    if validate_password_strength(new_password):
        return "weak_password", None
    now = datetime.now(UTC)
    token_row = await session.get(PasswordResetToken, token_id)
    if token_row is None:
        return "invalid_token", None
    if token_row.token_hash is not None:
        return "invalid_token", None
    if token_row.used_at is not None:
        return "invalid_token", None
    if token_row.expires_at <= now:
        return "expired_token", None
    if not verify_password_reset_hmac(
        token_row.id, token_row.user_id, token_row.expires_at, signature
    ):
        return "invalid_token", None

    user = await session.get(UserProfile, token_row.user_id)
    if user is None:
        return "user_not_found", None

    user.hashed_password = hash_password(new_password)
    user.token_version += 1
    token_row.used_at = now
    await session.commit()
    await session.refresh(user)
    return "ok", user


async def reset_password_by_token(
    session: AsyncSession,
    *,
    token: str,
    new_password: str,
) -> tuple[str, UserProfile | None]:
    if validate_password_strength(new_password):
        return "weak_password", None
    token_hash = _hash_token(token.strip())
    now = datetime.now(UTC)
    result = await session.execute(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash)
    )
    token_row = result.scalars().first()
    if token_row is None:
        return "invalid_token", None
    if token_row.used_at is not None:
        return "invalid_token", None
    if token_row.expires_at <= now:
        return "expired_token", None

    user = await session.get(UserProfile, token_row.user_id)
    if user is None:
        return "user_not_found", None

    user.hashed_password = hash_password(new_password)
    user.token_version += 1
    token_row.used_at = now
    await session.commit()
    await session.refresh(user)
    return "ok", user
