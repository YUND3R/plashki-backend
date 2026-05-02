import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Role, Subscription
from app.db.models import UserProfile


async def update_user_role_user_to_sponsor(
    session: AsyncSession,
    *,
    requester_id: uuid.UUID,
    user_id: uuid.UUID,
) -> bool:
    requester = await session.get(UserProfile, requester_id)
    if requester is None or requester.role != Role.ADMIN:
        return False
    user = await session.get(UserProfile, user_id)
    if user is None or user.role != Role.USER:
        return False
    user.role = Role.SPONSOR
    await session.commit()
    return True


async def delete_sponsor_role_from_user(
    session: AsyncSession,
    *,
    requester_id: uuid.UUID,
    user_id: uuid.UUID,
) -> bool:
    requester = await session.get(UserProfile, requester_id)
    if requester is None or requester.role != Role.ADMIN:
        return False
    user = await session.get(UserProfile, user_id)
    if user is None or user.role != Role.SPONSOR:
        return False
    user.role = Role.USER
    await session.commit()
    return True


async def update_user_role_user_to_moderator(
    session: AsyncSession,
    *,
    requester_id: uuid.UUID,
    user_id: uuid.UUID,
) -> bool:
    requester = await session.get(UserProfile, requester_id)
    if requester is None or requester.role != Role.ADMIN:
        return False
    user = await session.get(UserProfile, user_id)
    if user is None or user.role != Role.USER:
        return False
    user.role = Role.MODERATOR
    await session.commit()
    return True


async def delete_moderator_role_from_user(
    session: AsyncSession,
    *,
    requester_id: uuid.UUID,
    user_id: uuid.UUID,
) -> bool:
    requester = await session.get(UserProfile, requester_id)
    if requester is None or requester.role != Role.ADMIN:
        return False
    user = await session.get(UserProfile, user_id)
    if user is None or user.role != Role.MODERATOR:
        return False
    user.role = Role.USER
    await session.commit()
    return True


async def admin_update_user_access(
    session: AsyncSession,
    *,
    requester_id: uuid.UUID,
    user_id: uuid.UUID,
    role: Role | None = None,
    subscription: Subscription | None = None,
) -> tuple[str | None, UserProfile | None]:
    requester = await session.get(UserProfile, requester_id)
    if requester is None or requester.role != Role.ADMIN:
        return "not_admin", None
    user = await session.get(UserProfile, user_id)
    if user is None:
        return "user_not_found", None
    if role is None and subscription is None:
        return "empty_update", None

    if role is not None:
        user.role = role
    if subscription is not None:
        user.subscription = subscription
    await session.commit()
    await session.refresh(user)
    return None, user
