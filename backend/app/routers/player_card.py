import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.deps.auth import get_current_user_id
from app.schemas.list_filters import PlayerCardListFilters
from app.schemas.player_card import (
    PlayerCardPatch,
    PlayerCardPhotoResponse,
    PlayerCardPublic,
    PlayerCardWrite,
)
from app.services import player_card as player_card_service
from app.services.photo_storage import save_player_card_image

router = APIRouter(
    prefix="/users/{owner_user_id}/player-cards",
    tags=["player-cards"],
)


def _require_self(owner_user_id: uuid.UUID, current_user_id: uuid.UUID) -> None:
    if owner_user_id != current_user_id:
        raise HTTPException(
            status_code=403,
            detail="Можно работать только со своими карточками (owner_user_id из JWT).",
        )


@router.get(
    "",
    response_model=list[PlayerCardPublic],
    summary="Список карточек игроков владельца",
    description="Нужен Bearer JWT. owner_user_id в пути должен совпадать с пользователем из токена.",
)
async def list_player_cards(
    owner_user_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current_user_id: uuid.UUID = Depends(get_current_user_id),
    filters: PlayerCardListFilters = Depends(),
) -> list[PlayerCardPublic]:
    _require_self(owner_user_id, current_user_id)
    err, rows = await player_card_service.list_player_cards(
        session, owner_user_id, filters=filters
    )
    if err == "owner_not_found":
        raise HTTPException(status_code=404, detail="Владелец (пользователь) не найден")
    return [PlayerCardPublic.model_validate(r) for r in rows]


@router.post(
    "",
    response_model=PlayerCardPublic,
    summary="Создать карточку игрока",
)
async def create_player_card(
    owner_user_id: uuid.UUID,
    body: PlayerCardWrite,
    session: AsyncSession = Depends(get_session),
    current_user_id: uuid.UUID = Depends(get_current_user_id),
) -> PlayerCardPublic:
    _require_self(owner_user_id, current_user_id)
    err, row = await player_card_service.create_player_card(session, owner_user_id, body)
    if err == "owner_not_found":
        raise HTTPException(status_code=404, detail="Владелец (пользователь) не найден")
    assert row is not None
    return PlayerCardPublic.model_validate(row)


@router.post(
    "/{card_id}/photo",
    response_model=PlayerCardPhotoResponse,
    summary="Загрузить фото в эту карточку",
    description=(
        "multipart/form-data, поле **file**. Файл сохраняется, URL добавляется в **photo_urls** карточки "
        "(не больше 10). Нужен JWT; owner_user_id = пользователь из токена."
    ),
)
async def upload_photo_to_player_card(
    owner_user_id: uuid.UUID,
    card_id: uuid.UUID,
    request: Request,
    file: UploadFile = File(..., description="Изображение"),
    session: AsyncSession = Depends(get_session),
    current_user_id: uuid.UUID = Depends(get_current_user_id),
) -> PlayerCardPhotoResponse:
    _require_self(owner_user_id, current_user_id)
    url = await save_player_card_image(file, request)
    err, row = await player_card_service.add_photo_url_to_card(
        session, owner_user_id, card_id, url
    )
    if err == "not_found":
        raise HTTPException(status_code=404, detail="Карточка не найдена")
    if err == "too_many":
        raise HTTPException(
            status_code=409,
            detail="У карточки уже максимум фото (10). Удалите лишние через PATCH или замените список.",
        )
    if err == "url_too_long":
        raise HTTPException(status_code=400, detail="URL слишком длинный")
    assert row is not None
    return PlayerCardPhotoResponse(url=url, photo_urls=list(row.photo_urls))


@router.get(
    "/{card_id}",
    response_model=PlayerCardPublic,
    summary="Одна карточка",
)
async def get_player_card(
    owner_user_id: uuid.UUID,
    card_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current_user_id: uuid.UUID = Depends(get_current_user_id),
) -> PlayerCardPublic:
    _require_self(owner_user_id, current_user_id)
    row = await player_card_service.get_player_card(session, owner_user_id, card_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Карточка не найдена")
    return PlayerCardPublic.model_validate(row)


@router.put(
    "/{card_id}",
    response_model=PlayerCardPublic,
    summary="Полностью обновить карточку",
)
async def replace_player_card(
    owner_user_id: uuid.UUID,
    card_id: uuid.UUID,
    body: PlayerCardWrite,
    session: AsyncSession = Depends(get_session),
    current_user_id: uuid.UUID = Depends(get_current_user_id),
) -> PlayerCardPublic:
    _require_self(owner_user_id, current_user_id)
    err, row = await player_card_service.replace_player_card(
        session, owner_user_id, card_id, body
    )
    if err == "not_found":
        raise HTTPException(status_code=404, detail="Карточка не найдена")
    assert row is not None
    return PlayerCardPublic.model_validate(row)


@router.patch(
    "/{card_id}",
    response_model=PlayerCardPublic,
    summary="Частично обновить карточку",
)
async def patch_player_card(
    owner_user_id: uuid.UUID,
    card_id: uuid.UUID,
    body: PlayerCardPatch,
    session: AsyncSession = Depends(get_session),
    current_user_id: uuid.UUID = Depends(get_current_user_id),
) -> PlayerCardPublic:
    _require_self(owner_user_id, current_user_id)
    err, row = await player_card_service.patch_player_card(
        session, owner_user_id, card_id, body
    )
    if err == "not_found":
        raise HTTPException(status_code=404, detail="Карточка не найдена")
    assert row is not None
    return PlayerCardPublic.model_validate(row)


@router.delete(
    "/{card_id}",
    status_code=204,
    summary="Удалить карточку",
)
async def delete_player_card(
    owner_user_id: uuid.UUID,
    card_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current_user_id: uuid.UUID = Depends(get_current_user_id),
) -> None:
    _require_self(owner_user_id, current_user_id)
    err, ok = await player_card_service.delete_player_card(
        session, owner_user_id, card_id
    )
    if err == "not_found" or not ok:
        raise HTTPException(status_code=404, detail="Карточка не найдена")
