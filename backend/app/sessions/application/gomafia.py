import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import GameLobby, LobbyMembership, PlayerCard, UserProfile
from app.schemas.lobby import ImportedLobbyInfo, ImportGomafiaTournamentResponse
from app.sessions.ports.gomafia import (
    GomafiaFetchError,
    GomafiaTournamentSource,
    InvalidGomafiaUrl,
)
from app.sessions.providers import get_gomafia_source


async def _get_or_create_player_card_for_nickname(
    session: AsyncSession,
    owner_user_id: uuid.UUID,
    nickname: str,
) -> PlayerCard:
    result = await session.execute(
        select(PlayerCard)
        .where(
            PlayerCard.owner_user_id == owner_user_id,
            PlayerCard.nickname == nickname,
        )
        .limit(1)
    )
    card = result.scalars().first()
    if card is not None:
        return card
    card = PlayerCard(
        owner_user_id=owner_user_id,
        first_name=nickname[:100],
        last_name="",
        nickname=nickname[:255],
        club=None,
        gomafia_url=None,
        photo_urls=[],
    )
    session.add(card)
    await session.flush()
    return card


async def import_gomafia_tournament_to_lobbies(
    session: AsyncSession,
    *,
    acting_user_id: uuid.UUID,
    url: str,
    source: GomafiaTournamentSource | None = None,
) -> tuple[str | None, ImportGomafiaTournamentResponse | None]:
    source = source or get_gomafia_source()
    try:
        valid_url = source.validate_url(url)
    except InvalidGomafiaUrl:
        return "invalid_url", None
    if await session.get(UserProfile, acting_user_id) is None:
        return "host_not_found", None
    try:
        tournament = source.load(valid_url)
    except GomafiaFetchError:
        return "fetch_failed", None
    parsed_tables = tournament.tables
    if not parsed_tables:
        return "parse_failed", None

    title = tournament.title
    cards: dict[str, PlayerCard] = {}
    table_counts: dict[int, int] = {}
    for table in parsed_tables:
        table_counts[table.tour_no] = table_counts.get(table.tour_no, 0) + 1

    variants: list[dict] = []
    seen_tables: dict[int, int] = {}
    max_players = 10
    for table in parsed_tables:
        table_index = seen_tables.get(table.tour_no, 0) + 1
        seen_tables[table.tour_no] = table_index
        table_no = table.table_no if table.table_no is not None else table_index
        variant_title = f"Тур {table.tour_no}"
        if table_counts[table.tour_no] > 1:
            variant_title += f" — Стол {table_no}"
        max_players = max(
            max_players, max(seat.seat_no for seat in table.seats), 10
        )
        seats: list[dict] = []
        for seat in table.seats:
            card = cards.get(seat.nickname)
            if card is None:
                card = await _get_or_create_player_card_for_nickname(
                    session, acting_user_id, seat.nickname
                )
                cards[seat.nickname] = card
            seats.append(
                {
                    "seat_no": seat.seat_no,
                    "seat_order": seat.seat_no - 1,
                    "nickname": seat.nickname,
                    "player_card_id": str(card.id),
                }
            )
        variants.append(
            {
                "key": f"tour-{table.tour_no}-table-{table_no}",
                "title": variant_title[:120],
                "tour_no": table.tour_no,
                "table_label": f"Стол {table_no}",
                "players_count": len(table.seats),
                "seats": seats,
            }
        )
    if not variants:
        return "parse_failed", None

    first = variants[0]
    lobby = GameLobby(
        max_players=max_players,
        title=title[:120],
        host_user_id=acting_user_id,
        imported_source_url=tournament.source_url,
        imported_current_key=str(first["key"]),
        imported_variants=variants,
    )
    session.add(lobby)
    await session.flush()
    for seat in first["seats"]:
        session.add(
            LobbyMembership(
                lobby_id=lobby.id,
                player_card_id=uuid.UUID(str(seat["player_card_id"])),
                seat_order=int(seat["seat_order"]),
            )
        )
    await session.commit()
    return None, ImportGomafiaTournamentResponse(
        source_url=tournament.source_url,
        created_lobbies=[
            ImportedLobbyInfo(
                lobby_id=lobby.id,
                title=lobby.title,
                players_count=int(first["players_count"]),
            )
        ],
    )
