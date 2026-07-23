import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.commerce.application.overlay_designs import SqlAlchemyOverlayDesignAccess
from app.broadcast.application.overlay import (
    clear_lobby_best_move,
    clear_lobby_sheriff_check,
    get_active_overlay_state_for_user,
    get_lobby_overlay_state,
    get_lobby_overlay_state_by_public_id,
    get_overlay_design_catalog_for_user,
    get_overlay_design_options,
    set_active_overlay_lobby,
    set_lobby_active_overlay_screen,
    set_lobby_best_move,
    set_lobby_bonus_points,
    set_lobby_overlay_design,
    set_lobby_sheriff_check,
    set_lobby_victory_scores_visibility,
)
from app.db.base import OverlayDesign
from app.db.session import get_session
from app.deps.auth import get_current_user_id
from app.schemas.lobby import (
    ActiveOverlayLobbyResponse,
    GameLobbyPublic,
    LobbyOverlayDesignsResponse,
    LobbyOverlayStateResponse,
    OverlayDesignCatalogResponse,
    OverlayLiveStateResponse,
    SetActiveOverlayLobbyBody,
    SetActiveOverlayScreenBody,
    SetBestMoveBody,
    SetLobbyBonusPointsBody,
    SetOverlayDesignBody,
    SetSheriffCheckBody,
    SetVictoryScoresVisibilityBody,
)
from app.shared.api.http import set_no_cache_headers

router = APIRouter()


@router.get(
    "/lobbies/{lobby_id}/overlay-state",
    tags=["lobbies", "overlay"],
    response_model=LobbyOverlayStateResponse,
    summary="Состояние лобби для OBS overlay (только нужные поля, порядок по местам)",
)
async def get_lobby_overlay_state_endpoint(
    lobby_id: uuid.UUID,
    response: Response,
    session: AsyncSession = Depends(get_session),
    current_user_id: uuid.UUID = Depends(get_current_user_id),
) -> LobbyOverlayStateResponse:
    set_no_cache_headers(response)
    result = await get_lobby_overlay_state(
        session,
        lobby_id,
        SqlAlchemyOverlayDesignAccess(session),
        viewer_user_id=current_user_id,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Лобби не найдено")
    return result


@router.get(
    "/overlay/{overlay_design}/{overlay_public_id}",
    tags=["overlay"],
    response_model=LobbyOverlayStateResponse,
    summary="Состояние overlay по публичному id (и опционально lobby_id)",
)
async def get_overlay_state_by_public_id(
    overlay_design: OverlayDesign,
    overlay_public_id: uuid.UUID,
    response: Response,
    lobby_id: uuid.UUID | None = Query(
        default=None,
        description="Опционально: если передан, состояние вернётся только для этого lobby_id.",
    ),
    session: AsyncSession = Depends(get_session),
) -> LobbyOverlayStateResponse:
    set_no_cache_headers(response)
    result = await get_lobby_overlay_state_by_public_id(
        session,
        overlay_public_id,
        SqlAlchemyOverlayDesignAccess(session),
        expected_lobby_id=lobby_id,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Лобби для overlay не найдено")
    # Параметр дизайна в URL поддерживаем для совместимости с фронт-маршрутом.
    # Истинный выбранный дизайн всегда берём из БД.
    _ = overlay_design
    return result


@router.get(
    "/overlay/design-catalog",
    tags=["overlay"],
    response_model=OverlayDesignCatalogResponse,
    summary="Каталог дизайнов overlay для текущего пользователя",
)
async def get_overlay_design_catalog(
    session: AsyncSession = Depends(get_session),
    current_user_id: uuid.UUID = Depends(get_current_user_id),
) -> OverlayDesignCatalogResponse:
    result = await get_overlay_design_catalog_for_user(
        session, current_user_id, SqlAlchemyOverlayDesignAccess(session)
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return result


@router.patch(
    "/overlay/active-lobby",
    tags=["overlay"],
    response_model=ActiveOverlayLobbyResponse,
    summary="Сделать лобби активным для OBS live-ссылки",
)
async def patch_active_overlay_lobby(
    body: SetActiveOverlayLobbyBody,
    session: AsyncSession = Depends(get_session),
    acting_user_id: uuid.UUID = Depends(get_current_user_id),
) -> ActiveOverlayLobbyResponse:
    try:
        lobby_id = uuid.UUID(body.lobby_id.strip())
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail="Некорректный lobby_id (ожидается UUID)."
        ) from exc
    err, result = await set_active_overlay_lobby(session, acting_user_id, lobby_id)
    if err == "lobby_not_found":
        raise HTTPException(status_code=404, detail="Лобби не найдено")
    if err == "not_host":
        raise HTTPException(
            status_code=403,
            detail="Активировать лобби для OBS может только хост.",
        )
    if err == "user_not_found":
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    assert result is not None
    return result


@router.get(
    "/overlay/state",
    tags=["overlay"],
    response_model=OverlayLiveStateResponse,
    summary="Текущее active-lobby состояние для OBS (по текущему пользователю)",
)
async def get_overlay_state(
    session: AsyncSession = Depends(get_session),
    acting_user_id: uuid.UUID = Depends(get_current_user_id),
) -> OverlayLiveStateResponse:
    err, result = await get_active_overlay_state_for_user(session, acting_user_id)
    if err == "user_not_found":
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    assert result is not None
    return result


@router.get(
    "/overlay/live",
    tags=["overlay"],
    response_model=OverlayLiveStateResponse,
    summary="Стабильная live-ссылка для OBS (один URL)",
)
async def get_overlay_live(
    session: AsyncSession = Depends(get_session),
    acting_user_id: uuid.UUID = Depends(get_current_user_id),
) -> OverlayLiveStateResponse:
    err, result = await get_active_overlay_state_for_user(session, acting_user_id)
    if err == "user_not_found":
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    assert result is not None
    return result


@router.get(
    "/lobbies/{lobby_id}/overlay-designs",
    tags=["lobbies", "overlay"],
    response_model=LobbyOverlayDesignsResponse,
    summary="Доступные дизайны карточек overlay для лобби",
)
async def get_lobby_overlay_designs(
    lobby_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current_user_id: uuid.UUID = Depends(get_current_user_id),
) -> LobbyOverlayDesignsResponse:
    result = await get_overlay_design_options(
        session,
        lobby_id,
        SqlAlchemyOverlayDesignAccess(session),
        viewer_user_id=current_user_id,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Лобби не найдено")
    return result


@router.patch(
    "/lobbies/{lobby_id}/overlay-design",
    tags=["lobbies", "overlay"],
    response_model=GameLobbyPublic,
    summary="Выбрать дизайн карточек overlay для всего лобби (только хост)",
)
async def patch_lobby_overlay_design(
    lobby_id: uuid.UUID,
    body: SetOverlayDesignBody,
    session: AsyncSession = Depends(get_session),
    acting_user_id: uuid.UUID = Depends(get_current_user_id),
) -> GameLobbyPublic:
    err, lobby = await set_lobby_overlay_design(
        session,
        lobby_id,
        body.overlay_design,
        acting_user_id,
        SqlAlchemyOverlayDesignAccess(session),
    )
    if err == "lobby_not_found":
        raise HTTPException(status_code=404, detail="Лобби не найдено")
    if err == "not_host":
        raise HTTPException(
            status_code=403,
            detail="Менять дизайн overlay может только хост лобби.",
        )
    if err == "host_not_found":
        raise HTTPException(status_code=404, detail="Хост лобби не найден")
    if err == "unknown_design":
        raise HTTPException(status_code=404, detail="Дизайн overlay не найден")
    if err == "design_access_required":
        raise HTTPException(
            status_code=403,
            detail="Нет активной аренды этой плашки. Оплатите доступ в магазине.",
        )
    assert lobby is not None
    return lobby


@router.patch(
    "/lobbies/{lobby_id}/overlay-screen",
    tags=["lobbies", "overlay"],
    response_model=GameLobbyPublic,
    summary="Переключить активный экран для OBS в рамках лобби (только хост)",
)
async def patch_lobby_overlay_screen(
    lobby_id: uuid.UUID,
    body: SetActiveOverlayScreenBody,
    session: AsyncSession = Depends(get_session),
    acting_user_id: uuid.UUID = Depends(get_current_user_id),
) -> GameLobbyPublic:
    err, lobby = await set_lobby_active_overlay_screen(
        session, lobby_id, body.screen_key, acting_user_id
    )
    if err == "lobby_not_found":
        raise HTTPException(status_code=404, detail="Лобби не найдено")
    if err == "not_host":
        raise HTTPException(
            status_code=403,
            detail="Переключать экран overlay может только хост лобби.",
        )
    assert lobby is not None
    return lobby


@router.patch(
    "/lobbies/{lobby_id}/victory-scores",
    tags=["lobbies", "overlay"],
    response_model=GameLobbyPublic,
    summary="Переключить отображение баллов на экране победы",
)
async def patch_lobby_victory_scores_visibility(
    lobby_id: uuid.UUID,
    body: SetVictoryScoresVisibilityBody,
    session: AsyncSession = Depends(get_session),
    acting_user_id: uuid.UUID = Depends(get_current_user_id),
) -> GameLobbyPublic:
    err, lobby = await set_lobby_victory_scores_visibility(
        session, lobby_id, body.show_scores, acting_user_id
    )
    if err == "lobby_not_found":
        raise HTTPException(status_code=404, detail="Лобби не найдено")
    if err == "not_host":
        raise HTTPException(
            status_code=403, detail="Менять отображение баллов может только хост лобби."
        )
    assert lobby is not None
    return lobby


@router.patch(
    "/lobbies/{lobby_id}/sheriff-check",
    tags=["lobbies", "overlay"],
    response_model=GameLobbyPublic,
    summary="Обновить sheriff_check (5 значений), только хост",
)
async def patch_lobby_sheriff_check(
    lobby_id: uuid.UUID,
    body: SetSheriffCheckBody,
    session: AsyncSession = Depends(get_session),
    acting_user_id: uuid.UUID = Depends(get_current_user_id),
) -> GameLobbyPublic:
    err, lobby = await set_lobby_sheriff_check(
        session, lobby_id, body.sheriff_check, acting_user_id
    )
    if err == "lobby_not_found":
        raise HTTPException(status_code=404, detail="Лобби не найдено")
    if err == "not_host":
        raise HTTPException(
            status_code=403,
            detail="Менять sheriff_check может только хост лобби.",
        )
    assert lobby is not None
    return lobby


@router.delete(
    "/lobbies/{lobby_id}/sheriff-check",
    tags=["lobbies", "overlay"],
    response_model=GameLobbyPublic,
    summary="Сбросить sheriff_check, только хост",
)
async def delete_lobby_sheriff_check(
    lobby_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    acting_user_id: uuid.UUID = Depends(get_current_user_id),
) -> GameLobbyPublic:
    err, lobby = await clear_lobby_sheriff_check(session, lobby_id, acting_user_id)
    if err == "lobby_not_found":
        raise HTTPException(status_code=404, detail="Лобби не найдено")
    if err == "not_host":
        raise HTTPException(
            status_code=403,
            detail="Сбрасывать sheriff_check может только хост лобби.",
        )
    assert lobby is not None
    return lobby


@router.patch(
    "/lobbies/{lobby_id}/best-move",
    tags=["lobbies", "overlay"],
    response_model=GameLobbyPublic,
    summary="Обновить best_move (3 значения), только хост",
)
async def patch_lobby_best_move(
    lobby_id: uuid.UUID,
    body: SetBestMoveBody,
    session: AsyncSession = Depends(get_session),
    acting_user_id: uuid.UUID = Depends(get_current_user_id),
) -> GameLobbyPublic:
    err, lobby = await set_lobby_best_move(
        session, lobby_id, body.membership_id, body.best_move, acting_user_id
    )
    if err in {"lobby_not_found", "membership_not_found"}:
        raise HTTPException(status_code=404, detail="Лобби не найдено")
    if err == "not_host":
        raise HTTPException(
            status_code=403,
            detail="Менять best_move может только хост лобби.",
        )
    assert lobby is not None
    return lobby


@router.patch(
    "/lobbies/{lobby_id}/bonus-points",
    tags=["lobbies", "overlay"],
    response_model=GameLobbyPublic,
    summary="Сохранить доп. баллы игроков для экрана победы",
)
async def patch_lobby_bonus_points(
    lobby_id: uuid.UUID,
    body: SetLobbyBonusPointsBody,
    session: AsyncSession = Depends(get_session),
    acting_user_id: uuid.UUID = Depends(get_current_user_id),
) -> GameLobbyPublic:
    err, lobby = await set_lobby_bonus_points(
        session,
        lobby_id,
        [(entry.membership_id, entry.points) for entry in body.bonus_points],
        acting_user_id,
    )
    if err in {"lobby_not_found", "membership_not_found"}:
        raise HTTPException(status_code=404, detail="Лобби или игрок не найден")
    if err == "not_host":
        raise HTTPException(
            status_code=403, detail="Менять доп. баллы может только хост лобби."
        )
    if err == "duplicate_membership":
        raise HTTPException(
            status_code=422, detail="Игрок повторяется в списке баллов."
        )
    assert lobby is not None
    return lobby


@router.delete(
    "/lobbies/{lobby_id}/best-move",
    tags=["lobbies", "overlay"],
    response_model=GameLobbyPublic,
    summary="Сбросить best_move, только хост",
)
async def delete_lobby_best_move(
    lobby_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    acting_user_id: uuid.UUID = Depends(get_current_user_id),
) -> GameLobbyPublic:
    err, lobby = await clear_lobby_best_move(session, lobby_id, acting_user_id)
    if err == "lobby_not_found":
        raise HTTPException(status_code=404, detail="Лобби не найдено")
    if err == "not_host":
        raise HTTPException(
            status_code=403,
            detail="Сбрасывать best_move может только хост лобби.",
        )
    assert lobby is not None
    return lobby
