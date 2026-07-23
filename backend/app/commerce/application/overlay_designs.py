import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.commerce.application.contracts import OverlayDesignOption
from app.core.overlay_design_catalog import OVERLAY_DESIGN_CATALOG, get_catalog_entry
from app.db.base import OverlayDesign, Role
from app.db.models import UserOverlayDesignAccess, UserProfile


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def compute_rental_expires_at(
    *,
    rental_hours: int,
    now: datetime | None = None,
    current_expires_at: datetime | None = None,
) -> datetime:
    start = _as_utc(now or _utcnow())
    if current_expires_at is not None and _as_utc(current_expires_at) > start:
        return _as_utc(current_expires_at) + timedelta(hours=rental_hours)
    return start + timedelta(hours=rental_hours)


_UNLIMITED_DESIGN_ROLES = {Role.ADMIN, Role.SPONSOR}


def role_has_unlimited_design_access(role: Role) -> bool:
    return role in _UNLIMITED_DESIGN_ROLES


class SqlAlchemyOverlayDesignAccess:
    """Commerce adapter used by application services through the access port."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def _has_unlimited_access(self, user_id: uuid.UUID) -> bool:
        user = await self.session.get(UserProfile, user_id)
        return user is not None and role_has_unlimited_design_access(user.role)

    async def _access_row(
        self, user_id: uuid.UUID, design: OverlayDesign
    ) -> UserOverlayDesignAccess | None:
        result = await self.session.execute(
            select(UserOverlayDesignAccess).where(
                UserOverlayDesignAccess.user_id == user_id,
                UserOverlayDesignAccess.design_code == design.value,
            )
        )
        return result.scalar_one_or_none()

    async def can_use(self, user_id: uuid.UUID, design: OverlayDesign) -> bool:
        if await self._has_unlimited_access(user_id):
            return get_catalog_entry(design) is not None
        row = await self._access_row(user_id, design)
        return row is not None and _as_utc(row.expires_at) > _utcnow()

    async def host_has_access(
        self, host_user_id: uuid.UUID | None, design: OverlayDesign
    ) -> bool:
        return host_user_id is not None and await self.can_use(host_user_id, design)

    async def _active_access(self, user_id: uuid.UUID) -> dict[OverlayDesign, datetime]:
        result = await self.session.execute(
            select(UserOverlayDesignAccess).where(
                UserOverlayDesignAccess.user_id == user_id
            )
        )
        now = _utcnow()
        active: dict[OverlayDesign, datetime] = {}
        for row in result.scalars().all():
            expires_at = _as_utc(row.expires_at)
            if expires_at <= now:
                continue
            try:
                active[OverlayDesign(row.design_code)] = expires_at
            except ValueError:
                continue
        return active

    async def options_for_user(
        self, user_id: uuid.UUID | None
    ) -> list[OverlayDesignOption]:
        unlimited = user_id is not None and await self._has_unlimited_access(user_id)
        active = (
            {}
            if user_id is None or unlimited
            else await self._active_access(user_id)
        )
        return [
            OverlayDesignOption(
                code=design,
                title=entry.title,
                price_rub=entry.price_rub,
                rental_hours=entry.rental_hours,
                animations_supported=entry.animations_supported,
                selectable=unlimited or design in active,
                access_expires_at=None if unlimited else active.get(design),
                access_unlimited=unlimited,
            )
            for design, entry in OVERLAY_DESIGN_CATALOG.items()
        ]


async def list_user_design_access(
    session: AsyncSession, user_id: uuid.UUID
) -> list[dict]:
    result = await session.execute(
        select(UserOverlayDesignAccess)
        .where(UserOverlayDesignAccess.user_id == user_id)
        .order_by(UserOverlayDesignAccess.expires_at.desc())
    )
    now = _utcnow()
    items: list[dict] = []
    for row in result.scalars().all():
        try:
            design = OverlayDesign(row.design_code)
        except ValueError:
            continue
        entry = get_catalog_entry(design)
        if entry is None:
            continue
        expires_at = _as_utc(row.expires_at)
        items.append(
            {
                "design_code": design,
                "title": entry.title,
                "price_rub": entry.price_rub,
                "rental_hours": entry.rental_hours,
                "expires_at": expires_at,
                "is_active": expires_at > now,
            }
        )
    return items


async def grant_design_access(
    session: AsyncSession, *, user_id: uuid.UUID, design: OverlayDesign
) -> tuple[str | None, datetime | None]:
    entry = get_catalog_entry(design)
    if entry is None:
        return "unknown_design", None
    access = SqlAlchemyOverlayDesignAccess(session)
    row = await access._access_row(user_id, design)
    expires_at = compute_rental_expires_at(
        rental_hours=entry.rental_hours,
        current_expires_at=row.expires_at if row is not None else None,
    )
    if row is None:
        session.add(
            UserOverlayDesignAccess(
                user_id=user_id,
                design_code=design.value,
                expires_at=expires_at,
            )
        )
    else:
        row.expires_at = expires_at
    await session.commit()
    return None, expires_at
