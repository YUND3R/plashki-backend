import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.overlay_design_catalog import (
    OVERLAY_DESIGN_CATALOG,
    get_catalog_entry,
)
from app.db.base import OverlayDesign, Role
from app.db.models import UserOverlayDesignAccess, UserProfile
from app.schemas.lobby import LobbyOverlayDesignOption
from app.schemas.overlay_shop import (
    OverlayDesignShopCatalogResponse,
    OverlayDesignShopItem,
    UserOverlayDesignAccessListResponse,
    UserOverlayDesignAccessPublic,
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def compute_rental_expires_at(
    *,
    rental_hours: int,
    now: datetime | None = None,
    current_expires_at: datetime | None = None,
) -> datetime:
    """Продление аренды: от текущего конца + N часов, иначе от now + N часов."""
    start = _as_utc(now or _utcnow())
    if current_expires_at is not None and _as_utc(current_expires_at) > start:
        return _as_utc(current_expires_at) + timedelta(hours=rental_hours)
    return start + timedelta(hours=rental_hours)


_UNLIMITED_DESIGN_ROLES = {Role.ADMIN, Role.SPONSOR}


def role_has_unlimited_design_access(role: Role) -> bool:
    return role in _UNLIMITED_DESIGN_ROLES


async def user_has_unlimited_design_access(
    session: AsyncSession,
    user_id: uuid.UUID,
) -> bool:
    user = await session.get(UserProfile, user_id)
    if user is None:
        return False
    return role_has_unlimited_design_access(user.role)


async def get_access_row(
    session: AsyncSession,
    user_id: uuid.UUID,
    design: OverlayDesign,
) -> UserOverlayDesignAccess | None:
    result = await session.execute(
        select(UserOverlayDesignAccess).where(
            UserOverlayDesignAccess.user_id == user_id,
            UserOverlayDesignAccess.design_code == design.value,
        )
    )
    return result.scalar_one_or_none()


async def user_can_use_design(
    session: AsyncSession,
    user_id: uuid.UUID,
    design: OverlayDesign,
) -> bool:
    if await user_has_unlimited_design_access(session, user_id):
        return get_catalog_entry(design) is not None
    row = await get_access_row(session, user_id, design)
    if row is None:
        return False
    return _as_utc(row.expires_at) > _utcnow()


async def get_active_access_expires_map(
    session: AsyncSession,
    user_id: uuid.UUID,
) -> dict[OverlayDesign, datetime]:
    result = await session.execute(
        select(UserOverlayDesignAccess).where(UserOverlayDesignAccess.user_id == user_id)
    )
    now = _utcnow()
    out: dict[OverlayDesign, datetime] = {}
    for row in result.scalars().all():
        expires = _as_utc(row.expires_at)
        if expires <= now:
            continue
        try:
            design = OverlayDesign(row.design_code)
        except ValueError:
            continue
        out[design] = expires
    return out


async def build_design_options_for_user(
    session: AsyncSession,
    user_id: uuid.UUID | None,
) -> list[LobbyOverlayDesignOption]:
    unlimited = False
    active: dict[OverlayDesign, datetime] = {}
    if user_id is not None:
        unlimited = await user_has_unlimited_design_access(session, user_id)
        if not unlimited:
            active = await get_active_access_expires_map(session, user_id)
    options: list[LobbyOverlayDesignOption] = []
    for design, entry in OVERLAY_DESIGN_CATALOG.items():
        expires_at = None if unlimited else active.get(design)
        options.append(
            LobbyOverlayDesignOption(
                code=design,
                title=entry.title,
                price_rub=entry.price_rub,
                rental_hours=entry.rental_hours,
                animations_supported=entry.animations_supported,
                selectable=unlimited or expires_at is not None,
                access_expires_at=expires_at,
                access_unlimited=unlimited,
            )
        )
    return options


async def get_shop_catalog_for_user(
    session: AsyncSession,
    user_id: uuid.UUID,
) -> OverlayDesignShopCatalogResponse:
    options = await build_design_options_for_user(session, user_id)
    return OverlayDesignShopCatalogResponse(
        items=[OverlayDesignShopItem.model_validate(o.model_dump()) for o in options]
    )


async def list_user_design_access(
    session: AsyncSession,
    user_id: uuid.UUID,
) -> UserOverlayDesignAccessListResponse:
    result = await session.execute(
        select(UserOverlayDesignAccess)
        .where(UserOverlayDesignAccess.user_id == user_id)
        .order_by(UserOverlayDesignAccess.expires_at.desc())
    )
    now = _utcnow()
    items: list[UserOverlayDesignAccessPublic] = []
    for row in result.scalars().all():
        try:
            design = OverlayDesign(row.design_code)
        except ValueError:
            continue
        entry = get_catalog_entry(design)
        if entry is None:
            continue
        expires = _as_utc(row.expires_at)
        items.append(
            UserOverlayDesignAccessPublic(
                design_code=design,
                title=entry.title,
                price_rub=entry.price_rub,
                rental_hours=entry.rental_hours,
                expires_at=expires,
                is_active=expires > now,
            )
        )
    return UserOverlayDesignAccessListResponse(items=items)


async def grant_design_access(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    design: OverlayDesign,
) -> tuple[str | None, datetime | None]:
    """Выдать или продлить аренду плашки (вызывается после оплаты или admin-grant)."""
    entry = get_catalog_entry(design)
    if entry is None:
        return "unknown_design", None

    row = await get_access_row(session, user_id, design)
    new_expires = compute_rental_expires_at(
        rental_hours=entry.rental_hours,
        current_expires_at=row.expires_at if row is not None else None,
    )
    if row is None:
        row = UserOverlayDesignAccess(
            user_id=user_id,
            design_code=design.value,
            expires_at=new_expires,
        )
        session.add(row)
    else:
        row.expires_at = new_expires
    await session.commit()
    await session.refresh(row)
    return None, new_expires


async def host_has_active_design_access(
    session: AsyncSession,
    host_user_id: uuid.UUID | None,
    design: OverlayDesign,
) -> bool:
    if host_user_id is None:
        return False
    return await user_can_use_design(session, host_user_id, design)

