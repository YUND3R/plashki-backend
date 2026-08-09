import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.role import (
    admin_list_registered_users,
    admin_update_user_access,
    delete_moderator_role_from_user,
    delete_sponsor_role_from_user,
    update_user_role_user_to_moderator,
    update_user_role_user_to_sponsor,
)
from app.db.session import get_session
from app.deps.auth import get_current_user_id
from app.schemas.auth import (
    AdminRegisteredUser,
    AdminUpdateUserAccessBody,
    AdminUserAccessResponse,
)
from app.schemas.list_filters import AdminUserListFilters

router = APIRouter()


@router.patch(
    "/admin/users/{user_id}/sponsor",
    tags=["admin"],
    summary="USER → SPONSOR (только ADMIN)",
)
async def admin_set_sponsor(
    user_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    requester_id: uuid.UUID = Depends(get_current_user_id),
) -> dict[str, bool]:
    ok = await update_user_role_user_to_sponsor(
        session,
        requester_id=requester_id,
        user_id=user_id,
    )
    if not ok:
        raise HTTPException(
            status_code=403,
            detail="Нет прав или пользователь не в роли USER.",
        )
    return {"ok": True}


@router.delete(
    "/admin/users/{user_id}/sponsor",
    tags=["admin"],
    summary="SPONSOR → USER (только ADMIN)",
)
async def admin_delete_sponsor(
    user_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    requester_id: uuid.UUID = Depends(get_current_user_id),
) -> dict[str, bool]:
    ok = await delete_sponsor_role_from_user(
        session,
        requester_id=requester_id,
        user_id=user_id,
    )
    if not ok:
        raise HTTPException(
            status_code=403,
            detail="Нет прав или пользователь не в роли SPONSOR.",
        )
    return {"ok": True}


@router.patch(
    "/admin/users/{user_id}/moderator",
    tags=["admin"],
    summary="USER → MODERATOR (только ADMIN)",
)
async def admin_set_moderator(
    user_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    requester_id: uuid.UUID = Depends(get_current_user_id),
) -> dict[str, bool]:
    ok = await update_user_role_user_to_moderator(
        session,
        requester_id=requester_id,
        user_id=user_id,
    )
    if not ok:
        raise HTTPException(
            status_code=403,
            detail="Нет прав или пользователь не в роли USER.",
        )
    return {"ok": True}


@router.delete(
    "/admin/users/{user_id}/moderator",
    tags=["admin"],
    summary="MODERATOR → USER (только ADMIN)",
)
async def admin_delete_moderator(
    user_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    requester_id: uuid.UUID = Depends(get_current_user_id),
) -> dict[str, bool]:
    ok = await delete_moderator_role_from_user(
        session,
        requester_id=requester_id,
        user_id=user_id,
    )
    if not ok:
        raise HTTPException(
            status_code=403,
            detail="Нет прав или пользователь не в роли MODERATOR.",
        )
    return {"ok": True}


@router.patch(
    "/admin/users/{user_id}/access",
    tags=["admin"],
    response_model=AdminUserAccessResponse,
    summary="Обновить role/subscription пользователя (только ADMIN)",
)
async def admin_patch_user_access(
    user_id: uuid.UUID,
    body: AdminUpdateUserAccessBody,
    session: AsyncSession = Depends(get_session),
    requester_id: uuid.UUID = Depends(get_current_user_id),
) -> AdminUserAccessResponse:
    err, user = await admin_update_user_access(
        session,
        requester_id=requester_id,
        user_id=user_id,
        role=body.role,
        subscription=body.subscription,
    )
    if err == "not_admin":
        raise HTTPException(status_code=403, detail="Только ADMIN может менять доступ.")
    if err == "user_not_found":
        raise HTTPException(status_code=404, detail="Пользователь не найден.")
    if err == "empty_update":
        raise HTTPException(
            status_code=422,
            detail="Укажите хотя бы одно поле: role или subscription.",
        )
    if err == "admin_role_forbidden":
        raise HTTPException(
            status_code=422,
            detail="Роль ADMIN нельзя назначать через этот endpoint.",
        )
    assert user is not None
    return AdminUserAccessResponse(
        id=user.id,
        role=user.role,
        subscription=user.subscription,
    )


@router.get(
    "/admin/users",
    tags=["admin"],
    response_model=list[AdminRegisteredUser],
    summary="Список всех зарегистрированных пользователей (только ADMIN)",
)
async def admin_get_registered_users(
    session: AsyncSession = Depends(get_session),
    requester_id: uuid.UUID = Depends(get_current_user_id),
    filters: AdminUserListFilters = Depends(),
) -> list[AdminRegisteredUser]:
    err, users = await admin_list_registered_users(
        session,
        requester_id=requester_id,
        filters=filters,
    )
    if err == "not_admin":
        raise HTTPException(
            status_code=403,
            detail="Только ADMIN может смотреть список пользователей.",
        )
    return [AdminRegisteredUser.model_validate(user) for user in users]
