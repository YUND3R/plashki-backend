import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import LobbyMembership, PlayerCard, UserProfile
from app.schemas.player_card import (
    MAX_PLAYER_CARD_PHOTOS,
    PlayerCardPatch,
    PlayerCardWrite,
)


async def ensure_owner_exists(session: AsyncSession, owner_user_id: uuid.UUID) -> bool:
    user = await session.get(UserProfile, owner_user_id)
    return user is not None


async def list_player_cards(
    session: AsyncSession,
    owner_user_id: uuid.UUID,
) -> tuple[str | None, list[PlayerCard]]:
    if not await ensure_owner_exists(session, owner_user_id):
        return "owner_not_found", []
    result = await session.execute(
        select(PlayerCard)
        .where(PlayerCard.owner_user_id == owner_user_id)
        .order_by(PlayerCard.created_at.asc())
    )
    return None, list(result.scalars().all())


async def get_player_card(
    session: AsyncSession,
    owner_user_id: uuid.UUID,
    card_id: uuid.UUID,
) -> PlayerCard | None:
    row = await session.get(PlayerCard, card_id)
    if row is None or row.owner_user_id != owner_user_id:
        return None
    return row


async def create_player_card(
    session: AsyncSession,
    owner_user_id: uuid.UUID,
    body: PlayerCardWrite,
) -> tuple[str | None, PlayerCard | None]:
    if not await ensure_owner_exists(session, owner_user_id):
        return "owner_not_found", None
    row = PlayerCard(
        owner_user_id=owner_user_id,
        first_name=body.first_name,
        last_name=body.last_name,
        nickname=body.nickname,
        club=body.club,
        gomafia_url=body.gomafia_url,
        photo_urls=list(body.photo_urls),
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return None, row


async def replace_player_card(
    session: AsyncSession,
    owner_user_id: uuid.UUID,
    card_id: uuid.UUID,
    body: PlayerCardWrite,
) -> tuple[str | None, PlayerCard | None]:
    row = await get_player_card(session, owner_user_id, card_id)
    if row is None:
        return "not_found", None
    row.first_name = body.first_name
    row.last_name = body.last_name
    row.nickname = body.nickname
    row.club = body.club
    row.gomafia_url = body.gomafia_url
    row.photo_urls = list(body.photo_urls)
    await session.commit()
    await session.refresh(row)
    return None, row


async def patch_player_card(
    session: AsyncSession,
    owner_user_id: uuid.UUID,
    card_id: uuid.UUID,
    body: PlayerCardPatch,
) -> tuple[str | None, PlayerCard | None]:
    row = await get_player_card(session, owner_user_id, card_id)
    if row is None:
        return "not_found", None
    data = body.model_dump(exclude_unset=True)
    if "photo_urls" in data and data["photo_urls"] is not None:
        row.photo_urls = list(data.pop("photo_urls"))
    for key, val in data.items():
        setattr(row, key, val)
    await session.commit()
    await session.refresh(row)
    return None, row


async def add_photo_url_to_card(
    session: AsyncSession,
    owner_user_id: uuid.UUID,
    card_id: uuid.UUID,
    image_url: str,
) -> tuple[str | None, PlayerCard | None]:
    row = await get_player_card(session, owner_user_id, card_id)
    if row is None:
        return "not_found", None
    urls = list(row.photo_urls)
    if len(urls) >= MAX_PLAYER_CARD_PHOTOS:
        return "too_many", None
    if len(image_url) > 2048:
        return "url_too_long", None
    urls.append(image_url)
    row.photo_urls = urls
    await session.commit()
    await session.refresh(row)
    return None, row


async def delete_player_card(
    session: AsyncSession,
    owner_user_id: uuid.UUID,
    card_id: uuid.UUID,
) -> tuple[str | None, bool]:
    row = await get_player_card(session, owner_user_id, card_id)
    if row is None:
        return "not_found", False
    # В некоторых старых схемах ORM пытается проставить player_card_id = NULL в lobby_membership,
    # что ломается из-за NOT NULL. Явно удаляем связи перед удалением карточки.
    await session.execute(
        delete(LobbyMembership).where(LobbyMembership.player_card_id == card_id)
    )
    await session.delete(row)
    await session.commit()
    return None, True
