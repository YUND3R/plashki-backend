import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.commerce.application.overlay_designs import (
    SqlAlchemyOverlayDesignAccess,
    grant_design_access,
    list_user_design_access,
)
from app.core.overlay_design_catalog import get_catalog_entry
from app.db.base import Role
from app.db.models import UserProfile
from app.db.session import get_session
from app.deps.auth import get_current_user_id
from app.schemas.overlay_shop import (
    GrantOverlayDesignAccessBody,
    GrantOverlayDesignAccessResponse,
    OverlayDesignShopCatalogResponse,
    OverlayDesignShopItem,
    UserOverlayDesignAccessListResponse,
    UserOverlayDesignAccessPublic,
)

router = APIRouter(prefix="/shop", tags=["shop"])


@router.get(
    "/overlay-designs",
    response_model=OverlayDesignShopCatalogResponse,
    summary="Каталог плашек с ценами и статусом доступа",
)
async def get_overlay_design_shop_catalog(
    session: AsyncSession = Depends(get_session),
    user_id: uuid.UUID = Depends(get_current_user_id),
) -> OverlayDesignShopCatalogResponse:
    options = await SqlAlchemyOverlayDesignAccess(session).options_for_user(user_id)
    return OverlayDesignShopCatalogResponse(
        items=[
            OverlayDesignShopItem(
                code=option.code,
                title=option.title,
                price_rub=option.price_rub,
                rental_hours=option.rental_hours,
                animations_supported=option.animations_supported,
                selectable=option.selectable,
                access_expires_at=option.access_expires_at,
                access_unlimited=option.access_unlimited,
            )
            for option in options
        ]
    )


@router.get(
    "/me/overlay-designs",
    response_model=UserOverlayDesignAccessListResponse,
    summary="Мои аренды плашек (активные и истёкшие)",
)
async def get_my_overlay_design_access(
    session: AsyncSession = Depends(get_session),
    user_id: uuid.UUID = Depends(get_current_user_id),
) -> UserOverlayDesignAccessListResponse:
    items = await list_user_design_access(session, user_id)
    return UserOverlayDesignAccessListResponse(
        items=[UserOverlayDesignAccessPublic.model_validate(item) for item in items]
    )


@router.post(
    "/overlay-designs/purchase",
    response_model=GrantOverlayDesignAccessResponse,
    summary="Купить/продлить аренду плашки (имитация оплаты)",
)
async def purchase_overlay_design_access(
    body: GrantOverlayDesignAccessBody,
    session: AsyncSession = Depends(get_session),
    user_id: uuid.UUID = Depends(get_current_user_id),
) -> GrantOverlayDesignAccessResponse:
    entry = get_catalog_entry(body.design_code)
    if entry is None:
        raise HTTPException(status_code=404, detail="Дизайн overlay не найден.")

    err, expires_at = await grant_design_access(
        session,
        user_id=user_id,
        design=body.design_code,
    )
    if err == "unknown_design" or expires_at is None:
        raise HTTPException(status_code=404, detail="Дизайн overlay не найден.")

    return GrantOverlayDesignAccessResponse(
        user_id=user_id,
        design_code=body.design_code,
        expires_at=expires_at,
        price_rub=entry.price_rub,
        rental_hours=entry.rental_hours,
    )


@router.post(
    "/admin/users/{user_id}/overlay-design-access",
    response_model=GrantOverlayDesignAccessResponse,
    summary="[ADMIN] Выдать/продлить аренду плашки на 48ч (имитация оплаты)",
)
async def admin_grant_overlay_design_access(
    user_id: uuid.UUID,
    body: GrantOverlayDesignAccessBody,
    session: AsyncSession = Depends(get_session),
    requester_id: uuid.UUID = Depends(get_current_user_id),
) -> GrantOverlayDesignAccessResponse:
    requester = await session.get(UserProfile, requester_id)
    if requester is None or requester.role != Role.ADMIN:
        raise HTTPException(status_code=403, detail="Только ADMIN может выдавать доступ к плашкам.")

    target = await session.get(UserProfile, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден.")

    entry = get_catalog_entry(body.design_code)
    if entry is None:
        raise HTTPException(status_code=404, detail="Дизайн overlay не найден.")

    err, expires_at = await grant_design_access(
        session,
        user_id=user_id,
        design=body.design_code,
    )
    if err == "unknown_design" or expires_at is None:
        raise HTTPException(status_code=404, detail="Дизайн overlay не найден.")

    return GrantOverlayDesignAccessResponse(
        user_id=user_id,
        design_code=body.design_code,
        expires_at=expires_at,
        price_rub=entry.price_rub,
        rental_hours=entry.rental_hours,
    )
