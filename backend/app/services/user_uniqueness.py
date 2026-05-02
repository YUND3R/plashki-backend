import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import UserProfile


async def registration_conflict(
    session: AsyncSession,
    username: str,
    email: str,
    *,
    exclude_user_id: uuid.UUID | None = None,
) -> str | None:
    """Возвращает 'username' | 'email' если значение уже занято, иначе None."""
    q_user = select(UserProfile.id).where(UserProfile.username == username)
    q_mail = select(UserProfile.id).where(UserProfile.email == email)
    if exclude_user_id is not None:
        q_user = q_user.where(UserProfile.id != exclude_user_id)
        q_mail = q_mail.where(UserProfile.id != exclude_user_id)

    r1 = await session.execute(q_user.limit(1))
    if r1.first() is not None:
        return "username"
    r2 = await session.execute(q_mail.limit(1))
    if r2.first() is not None:
        return "email"
    return None
