import uuid

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Role, Subscription
from app.db.models import CommerceUserSubscription, UserProfile
from app.schemas.list_filters import AdminUserListFilters
from app.services.list_query import apply_pagination, apply_sort, ilike_pattern


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
        user.commerce_subscription.subscription = subscription
    await session.commit()
    await session.refresh(user)
    return None, user


async def admin_list_registered_users(
    session: AsyncSession,
    *,
    requester_id: uuid.UUID,
    filters: AdminUserListFilters | None = None,
) -> tuple[str | None, list[UserProfile]]:
    requester = await session.get(UserProfile, requester_id)
    if requester is None or requester.role != Role.ADMIN:
        return "not_admin", []

    filters = filters or AdminUserListFilters()
    stmt = select(UserProfile)
    if filters.q:
        pattern = ilike_pattern(filters.q)
        stmt = stmt.where(
            or_(
                UserProfile.username.ilike(pattern),
                UserProfile.email.ilike(pattern),
                UserProfile.nickname.ilike(pattern),
                UserProfile.first_name.ilike(pattern),
                UserProfile.last_name.ilike(pattern),
            )
        )
    if filters.role is not None:
        stmt = stmt.where(UserProfile.role == filters.role)
    if filters.subscription is not None:
        stmt = stmt.join(UserProfile.commerce_subscription).where(
            CommerceUserSubscription.subscription == filters.subscription
        )
    sort_column = {
        "created_at": UserProfile.created_at,
        "username": UserProfile.username,
        "email": UserProfile.email,
    }[filters.sort_by]
    stmt = apply_sort(stmt, sort_column, filters.sort_order)
    stmt = apply_pagination(stmt, limit=filters.limit, offset=filters.offset)
    result = await session.execute(stmt)
    return None, list(result.scalars().all())
