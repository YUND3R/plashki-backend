import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.base import GameRole, GameStatus
from app.db.models import GameLobby, LobbyMembership
from app.schemas.lobby import GameLobbyPublic
from app.sessions.application.lobbies import get_lobby_with_players, require_lobby_host
from app.sessions.application.roster import RosterPort, SqlAlchemyRoster


Result = tuple[str | None, GameLobbyPublic | None]


async def _result(session: AsyncSession, lobby_id: uuid.UUID) -> Result:
    return None, await get_lobby_with_players(session, lobby_id)


async def add_card_to_lobby(
    session: AsyncSession,
    lobby_id: uuid.UUID,
    player_card_id: uuid.UUID,
    acting_user_id: uuid.UUID,
    roster: RosterPort | None = None,
) -> Result:
    lobby = (
        await session.execute(
            select(GameLobby)
            .where(GameLobby.id == lobby_id)
            .options(selectinload(GameLobby.member_links))
        )
    ).scalar_one_or_none()
    if lobby is None:
        return "lobby_not_found", None
    card = await (roster or SqlAlchemyRoster(session)).get_card(player_card_id)
    if card is None:
        return "card_not_found", None
    if card.owner_user_id != acting_user_id:
        return "not_card_owner", None
    if len(lobby.member_links) >= lobby.max_players:
        return "lobby_full", None
    next_seat = max((member.seat_order for member in lobby.member_links), default=-1) + 1
    session.add(
        LobbyMembership(
            lobby_id=lobby_id,
            player_card_id=player_card_id,
            seat_order=next_seat,
        )
    )
    await session.commit()
    return await _result(session, lobby_id)


async def _membership_by_card(
    session: AsyncSession, lobby_id: uuid.UUID, player_card_id: uuid.UUID
) -> LobbyMembership | None:
    stmt = (
        select(LobbyMembership)
        .where(
            LobbyMembership.lobby_id == lobby_id,
            LobbyMembership.player_card_id == player_card_id,
        )
        .order_by(LobbyMembership.joined_at.desc())
    )
    return (await session.execute(stmt)).scalars().first()


async def _set_membership_value(
    session: AsyncSession,
    lobby_id: uuid.UUID,
    membership_id: uuid.UUID,
    acting_user_id: uuid.UUID,
    field: str,
    value,
) -> Result:
    err, _ = await require_lobby_host(session, lobby_id, acting_user_id)
    if err:
        return err, None
    membership = await session.get(LobbyMembership, membership_id)
    if membership is None or membership.lobby_id != lobby_id:
        return "membership_not_found", None
    setattr(membership, field, value)
    await session.commit()
    return await _result(session, lobby_id)


async def _set_card_membership_value(
    session: AsyncSession,
    lobby_id: uuid.UUID,
    player_card_id: uuid.UUID,
    acting_user_id: uuid.UUID,
    field: str,
    value,
) -> Result:
    err, _ = await require_lobby_host(session, lobby_id, acting_user_id)
    if err:
        return err, None
    membership = await _membership_by_card(session, lobby_id, player_card_id)
    if membership is None:
        return "membership_not_found", None
    setattr(membership, field, value)
    await session.commit()
    return await _result(session, lobby_id)


async def set_membership_game_role(
    session, lobby_id, player_card_id, game_role: GameRole, acting_user_id
) -> Result:
    return await _set_card_membership_value(
        session, lobby_id, player_card_id, acting_user_id, "game_role", game_role
    )


async def clear_membership_game_role(
    session, lobby_id, player_card_id, acting_user_id
) -> Result:
    return await _set_card_membership_value(
        session, lobby_id, player_card_id, acting_user_id, "game_role", None
    )


async def set_membership_game_role_for_seat(
    session, lobby_id, membership_id, game_role: GameRole, acting_user_id
) -> Result:
    return await _set_membership_value(
        session, lobby_id, membership_id, acting_user_id, "game_role", game_role
    )


async def clear_membership_game_role_for_seat(
    session, lobby_id, membership_id, acting_user_id
) -> Result:
    return await _set_membership_value(
        session, lobby_id, membership_id, acting_user_id, "game_role", None
    )


async def set_membership_status(
    session, lobby_id, player_card_id, status: GameStatus, acting_user_id
) -> Result:
    return await _set_card_membership_value(
        session, lobby_id, player_card_id, acting_user_id, "status", status
    )


async def clear_membership_status(
    session, lobby_id, player_card_id, acting_user_id
) -> Result:
    return await _set_card_membership_value(
        session, lobby_id, player_card_id, acting_user_id, "status", None
    )


async def set_membership_status_for_seat(
    session, lobby_id, membership_id, status: GameStatus, acting_user_id
) -> Result:
    return await _set_membership_value(
        session, lobby_id, membership_id, acting_user_id, "status", status
    )


async def clear_membership_status_for_seat(
    session, lobby_id, membership_id, acting_user_id
) -> Result:
    return await _set_membership_value(
        session, lobby_id, membership_id, acting_user_id, "status", None
    )


async def _clear_all(
    session: AsyncSession,
    lobby_id: uuid.UUID,
    acting_user_id: uuid.UUID,
    field: str,
) -> Result:
    err, _ = await require_lobby_host(session, lobby_id, acting_user_id)
    if err:
        return err, None
    await session.execute(
        update(LobbyMembership)
        .where(LobbyMembership.lobby_id == lobby_id)
        .values(**{field: None})
    )
    await session.commit()
    return await _result(session, lobby_id)


async def clear_all_lobby_game_roles(session, lobby_id, acting_user_id) -> Result:
    return await _clear_all(session, lobby_id, acting_user_id, "game_role")


async def clear_all_lobby_statuses(session, lobby_id, acting_user_id) -> Result:
    return await _clear_all(session, lobby_id, acting_user_id, "status")


async def swap_lobby_seats(
    session: AsyncSession,
    lobby_id: uuid.UUID,
    membership_id_a: uuid.UUID,
    membership_id_b: uuid.UUID,
    acting_user_id: uuid.UUID,
) -> Result:
    if membership_id_a == membership_id_b:
        return "same_seat", None
    err, _ = await require_lobby_host(session, lobby_id, acting_user_id)
    if err:
        return err, None
    first = await session.get(LobbyMembership, membership_id_a)
    second = await session.get(LobbyMembership, membership_id_b)
    if (
        first is None
        or second is None
        or first.lobby_id != lobby_id
        or second.lobby_id != lobby_id
    ):
        return "membership_not_found", None
    first.seat_order, second.seat_order = second.seat_order, first.seat_order
    await session.commit()
    return await _result(session, lobby_id)


async def replace_lobby_member_card(
    session: AsyncSession,
    lobby_id: uuid.UUID,
    membership_id: uuid.UUID,
    new_player_card_id: uuid.UUID,
    acting_user_id: uuid.UUID,
    roster: RosterPort | None = None,
) -> Result:
    err, _ = await require_lobby_host(session, lobby_id, acting_user_id)
    if err:
        return err, None
    membership = await session.get(LobbyMembership, membership_id)
    if membership is None or membership.lobby_id != lobby_id:
        return "membership_not_found", None
    if await (roster or SqlAlchemyRoster(session)).get_card(new_player_card_id) is None:
        return "card_not_found", None
    membership.player_card_id = new_player_card_id
    membership.lobby_photo_url = None
    await session.commit()
    return await _result(session, lobby_id)


async def set_lobby_member_display_photo(
    session: AsyncSession,
    lobby_id: uuid.UUID,
    membership_id: uuid.UUID,
    photo_url: str,
    acting_user_id: uuid.UUID,
    roster: RosterPort | None = None,
) -> Result:
    err, _ = await require_lobby_host(session, lobby_id, acting_user_id)
    if err:
        return err, None
    membership = await session.get(LobbyMembership, membership_id)
    if membership is None or membership.lobby_id != lobby_id:
        return "membership_not_found", None
    card = await (roster or SqlAlchemyRoster(session)).get_card(membership.player_card_id)
    if card is None:
        return "card_not_found", None
    photo = photo_url.strip()
    if photo not in card.photo_urls:
        return "invalid_photo_url", None
    membership.lobby_photo_url = photo
    await session.commit()
    return await _result(session, lobby_id)


async def clear_lobby_member_display_photo(
    session, lobby_id, membership_id, acting_user_id
) -> Result:
    return await _set_membership_value(
        session, lobby_id, membership_id, acting_user_id, "lobby_photo_url", None
    )
