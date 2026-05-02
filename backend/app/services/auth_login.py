from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.password import verify_password
from app.db.models import UserProfile


async def authenticate_by_login_or_email(
    session: AsyncSession,
    login: str,
    password: str,
) -> UserProfile | None:
    normalized = login.strip()
    if not normalized:
        return None

    if "@" in normalized:
        by_email = await session.execute(
            select(UserProfile).where(func.lower(UserProfile.email) == normalized.lower())
        )
        email_user = by_email.scalars().first()
        if email_user is not None and verify_password(password, email_user.hashed_password):
            return email_user

    by_username = await session.execute(
        select(UserProfile).where(UserProfile.username == normalized)
    )
    user = by_username.scalars().first()
    if user is None:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user
