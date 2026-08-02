import hashlib
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.link_signing import (
    sign_email_verification,
    sign_email_verification_pending,
    verify_email_hmac,
    verify_email_hmac_pending,
)
from app.db.base import Role, Subscription
from app.db.models import EmailVerificationToken, PendingRegistration, UserProfile

MAX_VERIFICATION_EMAILS = 5
VERIFICATION_EMAIL_COOLDOWN = timedelta(minutes=3)


def _hash_secret(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _expires_at() -> datetime:
    return datetime.now(UTC) + timedelta(minutes=settings.email_verification_token_ttl_minutes)


async def _check_send_limits_for_pending(
    session: AsyncSession,
    *,
    pending_id: uuid.UUID,
) -> str | None:
    now = datetime.now(UTC)
    stats = await session.execute(
        select(
            func.count(EmailVerificationToken.id),
            func.max(EmailVerificationToken.created_at),
        ).where(EmailVerificationToken.pending_registration_id == pending_id)
    )
    total, last_sent = stats.one()
    total = int(total or 0)
    if total >= MAX_VERIFICATION_EMAILS:
        return "limit"
    if last_sent is not None and last_sent > (now - VERIFICATION_EMAIL_COOLDOWN):
        return "cooldown"
    return None


async def _check_send_limits_for_user(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
) -> str | None:
    now = datetime.now(UTC)
    stats = await session.execute(
        select(
            func.count(EmailVerificationToken.id),
            func.max(EmailVerificationToken.created_at),
        ).where(EmailVerificationToken.user_id == user_id)
    )
    total, last_sent = stats.one()
    total = int(total or 0)
    if total >= MAX_VERIFICATION_EMAILS:
        return "limit"
    if last_sent is not None and last_sent > (now - VERIFICATION_EMAIL_COOLDOWN):
        return "cooldown"
    return None


async def create_verification_token_for_pending(
    session: AsyncSession,
    *,
    pending_id: uuid.UUID,
) -> tuple[str, tuple[uuid.UUID, str] | None]:
    pending = await session.get(PendingRegistration, pending_id)
    if pending is None or pending.consumed_at is not None:
        return "invalid", None
    if pending.expires_at <= datetime.now(UTC):
        return "expired", None
    limit_err = await _check_send_limits_for_pending(session, pending_id=pending.id)
    if limit_err is not None:
        return limit_err, None

    await session.execute(
        update(EmailVerificationToken)
        .where(
            and_(
                EmailVerificationToken.pending_registration_id == pending.id,
                EmailVerificationToken.used_at.is_(None),
            )
        )
        .values(used_at=datetime.now(UTC))
    )
    row = EmailVerificationToken(
        user_id=None,
        pending_registration_id=pending.id,
        token_hash=None,
        expires_at=pending.expires_at,
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)
    sig = sign_email_verification_pending(row.id, pending.id, row.expires_at)
    await session.commit()
    return "ok", (row.id, sig)


async def create_verification_token_for_user(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
) -> tuple[str, tuple[uuid.UUID, str] | None]:
    user = await session.get(UserProfile, user_id)
    if user is None or user.email_verified_at is not None:
        return "invalid", None
    limit_err = await _check_send_limits_for_user(session, user_id=user.id)
    if limit_err is not None:
        return limit_err, None
    now = datetime.now(UTC)
    exp = _expires_at()
    await session.execute(
        update(EmailVerificationToken)
        .where(
            and_(
                EmailVerificationToken.user_id == user.id,
                EmailVerificationToken.used_at.is_(None),
            )
        )
        .values(used_at=now)
    )
    row = EmailVerificationToken(
        user_id=user.id,
        pending_registration_id=None,
        token_hash=None,
        expires_at=exp,
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)
    sig = sign_email_verification(row.id, user.id, row.expires_at)
    await session.commit()
    return "ok", (row.id, sig)


async def verify_email_by_signed_link(
    session: AsyncSession,
    *,
    token_id: uuid.UUID,
    signature: str,
) -> tuple[str, UserProfile | None]:
    now = datetime.now(UTC)
    row = await session.get(EmailVerificationToken, token_id)
    if row is None or row.used_at is not None or row.expires_at <= now:
        return "invalid_token", None

    if row.pending_registration_id is not None:
        pending = await session.get(PendingRegistration, row.pending_registration_id)
        if pending is None or pending.consumed_at is not None:
            return "invalid_token", None
        if pending.expires_at <= now:
            return "expired_token", None
        if not verify_email_hmac_pending(row.id, pending.id, row.expires_at, signature):
            return "invalid_token", None

        user = UserProfile(
            username=pending.username,
            email=pending.email,
            first_name=pending.first_name,
            last_name=pending.last_name,
            avatar_url=pending.avatar_url,
            nickname=pending.username[:255],
            hashed_password=pending.hashed_password,
            role=Role.USER,
            subscription=Subscription.FREE,
            email_verified_at=now,
        )
        session.add(user)
        pending.consumed_at = now
        row.used_at = now
        await session.execute(
            update(EmailVerificationToken)
            .where(
                and_(
                    EmailVerificationToken.pending_registration_id == pending.id,
                    EmailVerificationToken.id != row.id,
                    EmailVerificationToken.used_at.is_(None),
                )
            )
            .values(used_at=now)
        )
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            return "conflict", None
        await session.refresh(user)
        return "ok", user

    if row.user_id is None:
        return "invalid_token", None
    if not verify_email_hmac(row.id, row.user_id, row.expires_at, signature):
        return "invalid_token", None
    user = await session.get(UserProfile, row.user_id)
    if user is None:
        return "user_not_found", None
    if user.email_verified_at is None:
        user.email_verified_at = now
    row.used_at = now
    await session.commit()
    await session.refresh(user)
    return "ok", user


async def verify_email_by_token(
    session: AsyncSession,
    *,
    token: str,
) -> tuple[str, UserProfile | None]:
    """Legacy: старые письма с raw token."""
    secret = token.strip()
    if not secret:
        return "invalid_token", None
    token_hash = _hash_secret(secret)
    now = datetime.now(UTC)
    result = await session.execute(
        select(EmailVerificationToken).where(EmailVerificationToken.token_hash == token_hash)
    )
    token_row = result.scalars().first()
    if token_row is None or token_row.used_at is not None or token_row.expires_at <= now:
        return "invalid_token", None
    if token_row.user_id is None:
        return "invalid_token", None
    user = await session.get(UserProfile, token_row.user_id)
    if user is None:
        return "user_not_found", None
    if user.email_verified_at is None:
        user.email_verified_at = now
    token_row.used_at = now
    await session.commit()
    await session.refresh(user)
    return "ok", user


async def create_verification_token_for_email(
    session: AsyncSession,
    *,
    email: str,
) -> tuple[str | None, tuple[uuid.UUID, str] | None, str | None, str | None]:
    normalized = email.strip().lower()
    now = datetime.now(UTC)
    p_res = await session.execute(
        select(PendingRegistration)
        .where(
            and_(
                func.lower(PendingRegistration.email) == normalized,
                PendingRegistration.consumed_at.is_(None),
                PendingRegistration.expires_at > now,
            )
        )
        .order_by(PendingRegistration.created_at.desc())
    )
    pending = p_res.scalars().first()
    if pending is not None:
        status, pair = await create_verification_token_for_pending(
            session, pending_id=pending.id
        )
        if status == "ok":
            return pending.email, pair, None, pending.username
        if status in {"cooldown", "limit"}:
            return pending.email, None, status, pending.username
        return None, None, None, None

    u_res = await session.execute(
        select(UserProfile).where(func.lower(UserProfile.email) == normalized)
    )
    user = u_res.scalars().first()
    if user is None or user.email_verified_at is not None:
        return None, None, None, None
    status, pair = await create_verification_token_for_user(session, user_id=user.id)
    if status == "ok":
        return user.email, pair, None, user.username
    if status in {"cooldown", "limit"}:
        return user.email, None, status, user.username
    return None, None, None, None
