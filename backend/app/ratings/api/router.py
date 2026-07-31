import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.deps.auth import get_current_user_id
from app.ratings.application.ratings import (
    add_rating_participants,
    create_rating_game,
    create_rating,
    delete_rating,
    get_rating_game,
    list_rating_games,
    get_rating,
    get_rating_table,
    list_ratings,
    sync_rating_from_lobby,
    update_rating,
)
from app.schemas.rating import (
    RatingAddParticipantsBody,
    RatingGamePublic,
    RatingGameListResponse,
    RatingGameWrite,
    RatingListItem,
    RatingPatch,
    RatingPublic,
    RatingSyncLobbyBody,
    RatingTableResponse,
    RatingWrite,
)

router = APIRouter(prefix="/ratings", tags=["ratings"])


@router.get(
    "",
    response_model=list[RatingListItem],
    summary="Список рейтингов текущего пользователя",
)
async def get_ratings(
    session: AsyncSession = Depends(get_session),
    current_user_id: uuid.UUID = Depends(get_current_user_id),
) -> list[RatingListItem]:
    err, rows = await list_ratings(session, current_user_id)
    if err == "owner_not_found":
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return rows


@router.post(
    "",
    response_model=RatingPublic,
    summary="Создать рейтинг",
    description=(
        "Укажите название, дату и список карточек игроков с аккаунта. "
        "Количество игроков не ограничено."
    ),
)
async def post_rating(
    body: RatingWrite,
    session: AsyncSession = Depends(get_session),
    current_user_id: uuid.UUID = Depends(get_current_user_id),
) -> RatingPublic:
    err, row = await create_rating(session, current_user_id, body)
    if err == "owner_not_found":
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    if err == "player_card_not_found":
        raise HTTPException(
            status_code=422,
            detail="Один или несколько игроков не найдены среди ваших карточек.",
        )
    assert row is not None
    return row


@router.get(
    "/{rating_id}",
    response_model=RatingPublic,
    summary="Один рейтинг с участниками",
)
async def get_rating_by_id(
    rating_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current_user_id: uuid.UUID = Depends(get_current_user_id),
) -> RatingPublic:
    err, row = await get_rating(session, current_user_id, rating_id)
    if err == "not_found":
        raise HTTPException(status_code=404, detail="Рейтинг не найден")
    assert row is not None
    return row


@router.get(
    "/{rating_id}/games",
    response_model=RatingGameListResponse,
    summary="Список игр рейтинга",
)
async def get_rating_games(
    rating_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current_user_id: uuid.UUID = Depends(get_current_user_id),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    sort: Literal["-played_at", "played_at", "-created_at", "created_at"] = Query(
        default="-played_at"
    ),
    q: str = Query(default="", max_length=255),
) -> RatingGameListResponse:
    err, payload = await list_rating_games(
        session,
        current_user_id,
        rating_id,
        limit=limit,
        offset=offset,
        sort=sort,
        q=q,
    )
    if err == "not_found":
        raise HTTPException(status_code=404, detail="Рейтинг не найден")
    assert payload is not None
    return payload


@router.get(
    "/{rating_id}/games/{game_id}",
    response_model=RatingGamePublic,
    summary="Одна игра рейтинга с результатами",
)
async def get_rating_game_by_id(
    rating_id: uuid.UUID,
    game_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current_user_id: uuid.UUID = Depends(get_current_user_id),
) -> RatingGamePublic:
    err, row = await get_rating_game(session, current_user_id, rating_id, game_id)
    if err == "not_found":
        raise HTTPException(status_code=404, detail="Игра рейтинга не найдена")
    assert row is not None
    return row


@router.patch(
    "/{rating_id}",
    response_model=RatingPublic,
    summary="Обновить рейтинг",
)
async def patch_rating(
    rating_id: uuid.UUID,
    body: RatingPatch,
    session: AsyncSession = Depends(get_session),
    current_user_id: uuid.UUID = Depends(get_current_user_id),
) -> RatingPublic:
    err, row = await update_rating(session, current_user_id, rating_id, body)
    if err == "not_found":
        raise HTTPException(status_code=404, detail="Рейтинг не найден")
    if err == "player_card_not_found":
        raise HTTPException(
            status_code=422,
            detail="Один или несколько игроков не найдены среди ваших карточек.",
        )
    assert row is not None
    return row


@router.post(
    "/{rating_id}/participants",
    response_model=RatingPublic,
    summary="Добавить игроков в рейтинг",
)
async def post_rating_participants(
    rating_id: uuid.UUID,
    body: RatingAddParticipantsBody,
    session: AsyncSession = Depends(get_session),
    current_user_id: uuid.UUID = Depends(get_current_user_id),
) -> RatingPublic:
    err, row = await add_rating_participants(session, current_user_id, rating_id, body)
    if err == "not_found":
        raise HTTPException(status_code=404, detail="Рейтинг не найден")
    if err == "player_card_not_found":
        raise HTTPException(
            status_code=422,
            detail="Один или несколько игроков не найдены среди ваших карточек.",
        )
    assert row is not None
    return row


@router.post(
    "/{rating_id}/games",
    response_model=RatingGamePublic,
    summary="Добавить игру в рейтинг",
    description=(
        "Добавляет одну игру в рейтинг и результаты по игрокам: роль, доп. баллы и итоговые баллы."
    ),
)
async def post_rating_game(
    rating_id: uuid.UUID,
    body: RatingGameWrite,
    session: AsyncSession = Depends(get_session),
    current_user_id: uuid.UUID = Depends(get_current_user_id),
) -> RatingGamePublic:
    err, row = await create_rating_game(session, current_user_id, rating_id, body)
    if err == "not_found":
        raise HTTPException(status_code=404, detail="Рейтинг не найден")
    if err == "player_not_in_rating":
        raise HTTPException(
            status_code=422,
            detail="Один или несколько игроков не входят в этот рейтинг.",
        )
    assert row is not None
    return row


@router.post(
    "/{rating_id}/sync-lobby",
    response_model=RatingGamePublic,
    summary="Синхронизировать игру из лобби в рейтинг",
    description=(
        "Берет игроков, роли и доп. баллы из лобби, добавляет отсутствующих игроков "
        "в рейтинг и создает игру рейтинга."
    ),
)
async def post_sync_lobby_to_rating(
    rating_id: uuid.UUID,
    body: RatingSyncLobbyBody,
    session: AsyncSession = Depends(get_session),
    current_user_id: uuid.UUID = Depends(get_current_user_id),
) -> RatingGamePublic:
    err, row = await sync_rating_from_lobby(session, current_user_id, rating_id, body)
    if err == "rating_not_found":
        raise HTTPException(status_code=404, detail="Рейтинг не найден")
    if err == "lobby_not_found":
        raise HTTPException(status_code=404, detail="Лобби не найдено")
    if err == "not_lobby_host":
        raise HTTPException(
            status_code=403,
            detail="Синхронизировать можно только лобби, где вы хост.",
        )
    if err == "lobby_empty":
        raise HTTPException(status_code=422, detail="В лобби нет игроков.")
    if err == "role_not_set":
        raise HTTPException(
            status_code=422,
            detail="У части игроков не задана игровая роль. Заполните роли в лобби.",
        )
    assert row is not None
    return row


@router.get(
    "/{rating_id}/table",
    response_model=RatingTableResponse,
    summary="Таблица рейтинга по игрокам",
)
async def get_rating_table_endpoint(
    rating_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current_user_id: uuid.UUID = Depends(get_current_user_id),
) -> RatingTableResponse:
    err, row = await get_rating_table(session, current_user_id, rating_id)
    if err == "not_found":
        raise HTTPException(status_code=404, detail="Рейтинг не найден")
    assert row is not None
    return row


@router.delete(
    "/{rating_id}",
    status_code=204,
    summary="Удалить рейтинг",
)
async def delete_rating_by_id(
    rating_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current_user_id: uuid.UUID = Depends(get_current_user_id),
) -> None:
    err, _ = await delete_rating(session, current_user_id, rating_id)
    if err == "not_found":
        raise HTTPException(status_code=404, detail="Рейтинг не найден")
