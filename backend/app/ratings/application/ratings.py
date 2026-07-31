import uuid

from sqlalchemy import asc, delete, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.base import GameRole, RatingGameSource, RatingWinnerSide
from app.db.models import (
    GameLobby,
    LobbyMembership,
    PlayerCard,
    Rating,
    RatingGame,
    RatingGameResult,
    RatingParticipant,
    UserProfile,
)
from app.schemas.rating import (
    RatingAddParticipantsBody,
    RatingGameListItem,
    RatingGameListResponse,
    RatingGamePublic,
    RatingGameResultPublic,
    RatingSyncLobbyBody,
    RatingGameWrite,
    RatingListItem,
    RatingPatch,
    RatingParticipantPublic,
    RatingPublic,
    RatingTableResponse,
    RatingTableRow,
    RatingWrite,
)

_BLACK_ROLES = {GameRole.MAFIA, GameRole.DON}
_RED_ROLES = {GameRole.PEACEFUL, GameRole.SHERIFF}
_MIN_GAMES_FOR_ROLE_AWARD = 3


def normalize_best_move(raw: list[str] | None) -> list[str]:
    values = (raw or [])[:3]
    normalized = [(value or "").strip() for value in values]
    normalized.extend([""] * (3 - len(normalized)))
    return normalized


def _seat_role_map(game_results) -> dict[int, GameRole]:
    mapping: dict[int, GameRole] = {}
    for game_result in game_results:
        mapping[int(game_result.sort_order) + 1] = game_result.role
    return mapping


def count_correct_mafia_hits(best_move: list[str] | None, game_results) -> int:
    seat_roles = _seat_role_map(game_results)
    hits = 0
    for value in normalize_best_move(best_move):
        if not value:
            continue
        try:
            seat_num = int(value.strip())
        except ValueError:
            continue
        if seat_num < 1:
            continue
        if seat_roles.get(seat_num) in _BLACK_ROLES:
            hits += 1
    return hits


def has_best_move(best_move: list[str] | None) -> bool:
    return any(normalize_best_move(best_move))


def _assign_role_award_flags(rows: list[RatingTableRow]) -> None:
    role_specs = [
        ("games_mafia", "avg_points_mafia", "total_points_mafia_sum", "is_best_mafia"),
        (
            "games_peaceful",
            "avg_points_peaceful",
            "total_points_peaceful_sum",
            "is_best_peaceful",
        ),
        (
            "games_sheriff",
            "avg_points_sheriff",
            "total_points_sheriff_sum",
            "is_best_sheriff",
        ),
        ("games_don", "avg_points_don", "total_points_don_sum", "is_best_don"),
    ]
    for games_field, avg_field, sum_field, best_field in role_specs:
        eligible = [
            row
            for row in rows
            if getattr(row, games_field) >= _MIN_GAMES_FOR_ROLE_AWARD
        ]
        if not eligible:
            continue
        best_key = max(
            (
                (
                    getattr(row, avg_field),
                    getattr(row, games_field),
                    getattr(row, sum_field),
                )
                for row in eligible
            ),
        )
        for row in eligible:
            row_key = (
                getattr(row, avg_field),
                getattr(row, games_field),
                getattr(row, sum_field),
            )
            if row_key == best_key:
                setattr(row, best_field, True)


async def _ensure_owner_exists(session: AsyncSession, owner_user_id: uuid.UUID) -> bool:
    return await session.get(UserProfile, owner_user_id) is not None


async def _validate_player_cards(
    session: AsyncSession,
    owner_user_id: uuid.UUID,
    player_card_ids: list[uuid.UUID],
) -> str | None:
    if not player_card_ids:
        return None
    rows = (
        await session.execute(
            select(PlayerCard.id).where(
                PlayerCard.owner_user_id == owner_user_id,
                PlayerCard.id.in_(player_card_ids),
            )
        )
    ).scalars().all()
    if len(rows) != len(set(player_card_ids)):
        return "player_card_not_found"
    return None


def _participant_public(row: RatingParticipant) -> RatingParticipantPublic:
    card = row.player_card
    return RatingParticipantPublic(
        id=row.id,
        player_card_id=row.player_card_id,
        sort_order=row.sort_order,
        nickname=card.nickname,
        first_name=card.first_name,
        last_name=card.last_name,
        club=card.club,
    )


def _rating_public(row: Rating) -> RatingPublic:
    return RatingPublic(
        id=row.id,
        owner_user_id=row.owner_user_id,
        name=row.name,
        event_date=row.event_date,
        participants=[_participant_public(participant) for participant in row.participants],
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _game_public(row: RatingGame) -> RatingGamePublic:
    return RatingGamePublic(
        id=row.id,
        rating_id=row.rating_id,
        title=row.title,
        played_at=row.played_at,
        winner_side=row.winner_side,
        source=row.source,
        lobby_id=row.lobby_id,
        created_at=row.created_at,
        results=[
            RatingGameResultPublic(
                player_card_id=result.player_card_id,
                nickname=result.player_card.nickname,
                first_name=result.player_card.first_name,
                last_name=result.player_card.last_name,
                role=result.role,
                bonus_points=float(result.bonus_points),
                total_points=float(result.total_points),
                best_move=normalize_best_move(result.best_move),
            )
            for result in row.results
        ],
    )


async def _get_owned_rating(
    session: AsyncSession,
    owner_user_id: uuid.UUID,
    rating_id: uuid.UUID,
    *,
    with_games: bool = False,
) -> Rating | None:
    opts = [selectinload(Rating.participants).selectinload(RatingParticipant.player_card)]
    if with_games:
        opts.append(
            selectinload(Rating.games)
            .selectinload(RatingGame.results)
            .selectinload(RatingGameResult.player_card)
        )
    row = (
        await session.execute(
            select(Rating)
            .where(Rating.id == rating_id, Rating.owner_user_id == owner_user_id)
            .options(*opts)
        )
    ).scalar_one_or_none()
    return row


async def _ensure_owned_rating(
    session: AsyncSession, owner_user_id: uuid.UUID, rating_id: uuid.UUID
) -> bool:
    exists = (
        await session.execute(
            select(Rating.id).where(
                Rating.id == rating_id,
                Rating.owner_user_id == owner_user_id,
            )
        )
    ).scalar_one_or_none()
    return exists is not None


async def list_rating_games(
    session: AsyncSession,
    owner_user_id: uuid.UUID,
    rating_id: uuid.UUID,
    *,
    limit: int = 50,
    offset: int = 0,
    sort: str = "-played_at",
    q: str = "",
) -> tuple[str | None, RatingGameListResponse | None]:
    if not await _ensure_owned_rating(session, owner_user_id, rating_id):
        return "not_found", None

    where_clause = [RatingGame.rating_id == rating_id]
    query = q.strip()
    if query:
        where_clause.append(RatingGame.title.ilike(f"%{query}%"))

    order_by = [desc(RatingGame.played_at), desc(RatingGame.created_at)]
    if sort == "played_at":
        order_by = [asc(RatingGame.played_at), asc(RatingGame.created_at)]
    elif sort == "-created_at":
        order_by = [desc(RatingGame.created_at)]
    elif sort == "created_at":
        order_by = [asc(RatingGame.created_at)]

    total = (
        await session.execute(
            select(func.count(RatingGame.id)).where(*where_clause)
        )
    ).scalar_one()

    games = (
        await session.execute(
            select(RatingGame)
            .where(*where_clause)
            .options(selectinload(RatingGame.results))
            .order_by(*order_by)
            .offset(offset)
            .limit(limit)
        )
    ).scalars().all()

    items = [
        RatingGameListItem(
            id=game.id,
            title=game.title,
            played_at=game.played_at,
            winner_side=game.winner_side,
            players_count=len(game.results),
            source=game.source,
            lobby_id=game.lobby_id,
            created_at=game.created_at,
        )
        for game in games
    ]
    return None, RatingGameListResponse(rating_id=rating_id, total=int(total), items=items)


async def get_rating_game(
    session: AsyncSession,
    owner_user_id: uuid.UUID,
    rating_id: uuid.UUID,
    game_id: uuid.UUID,
) -> tuple[str | None, RatingGamePublic | None]:
    game = (
        await session.execute(
            select(RatingGame)
            .join(Rating, Rating.id == RatingGame.rating_id)
            .where(
                RatingGame.id == game_id,
                RatingGame.rating_id == rating_id,
                Rating.owner_user_id == owner_user_id,
            )
            .options(
                selectinload(RatingGame.results).selectinload(RatingGameResult.player_card),
            )
        )
    ).scalar_one_or_none()
    if game is None:
        return "not_found", None
    return None, _game_public(game)


async def _replace_participants(
    session: AsyncSession,
    rating: Rating,
    player_card_ids: list[uuid.UUID],
) -> None:
    await session.execute(delete(RatingParticipant).where(RatingParticipant.rating_id == rating.id))
    for index, player_card_id in enumerate(player_card_ids):
        session.add(
            RatingParticipant(
                rating_id=rating.id,
                player_card_id=player_card_id,
                sort_order=index,
            )
        )


async def list_ratings(
    session: AsyncSession, owner_user_id: uuid.UUID
) -> tuple[str | None, list[RatingListItem]]:
    if not await _ensure_owner_exists(session, owner_user_id):
        return "owner_not_found", []
    participant_count = func.count(RatingParticipant.id).label("participant_count")
    rows = (
        await session.execute(
            select(Rating, participant_count)
            .outerjoin(RatingParticipant, RatingParticipant.rating_id == Rating.id)
            .where(Rating.owner_user_id == owner_user_id)
            .group_by(Rating.id)
            .order_by(Rating.event_date.desc(), Rating.created_at.desc())
        )
    ).all()
    return None, [
        RatingListItem(
            id=rating.id,
            name=rating.name,
            event_date=rating.event_date,
            participant_count=int(count),
            created_at=rating.created_at,
            updated_at=rating.updated_at,
        )
        for rating, count in rows
    ]


async def create_rating(
    session: AsyncSession,
    owner_user_id: uuid.UUID,
    body: RatingWrite,
) -> tuple[str | None, RatingPublic | None]:
    if not await _ensure_owner_exists(session, owner_user_id):
        return "owner_not_found", None
    card_err = await _validate_player_cards(session, owner_user_id, body.player_card_ids)
    if card_err:
        return card_err, None
    rating = Rating(owner_user_id=owner_user_id, name=body.name, event_date=body.event_date)
    session.add(rating)
    await session.flush()
    await _replace_participants(session, rating, body.player_card_ids)
    await session.commit()
    loaded = await _get_owned_rating(session, owner_user_id, rating.id)
    assert loaded is not None
    return None, _rating_public(loaded)


async def get_rating(
    session: AsyncSession, owner_user_id: uuid.UUID, rating_id: uuid.UUID
) -> tuple[str | None, RatingPublic | None]:
    row = await _get_owned_rating(session, owner_user_id, rating_id)
    if row is None:
        return "not_found", None
    return None, _rating_public(row)


async def update_rating(
    session: AsyncSession,
    owner_user_id: uuid.UUID,
    rating_id: uuid.UUID,
    body: RatingPatch,
) -> tuple[str | None, RatingPublic | None]:
    row = await _get_owned_rating(session, owner_user_id, rating_id)
    if row is None:
        return "not_found", None
    data = body.model_dump(exclude_unset=True)
    player_card_ids = data.pop("player_card_ids", None)
    if player_card_ids is not None:
        card_err = await _validate_player_cards(session, owner_user_id, player_card_ids)
        if card_err:
            return card_err, None
        await _replace_participants(session, row, player_card_ids)
    if "name" in data:
        row.name = data["name"]
    if "event_date" in data:
        row.event_date = data["event_date"]
    await session.commit()
    loaded = await _get_owned_rating(session, owner_user_id, rating_id)
    assert loaded is not None
    return None, _rating_public(loaded)


async def add_rating_participants(
    session: AsyncSession,
    owner_user_id: uuid.UUID,
    rating_id: uuid.UUID,
    body: RatingAddParticipantsBody,
) -> tuple[str | None, RatingPublic | None]:
    row = await _get_owned_rating(session, owner_user_id, rating_id)
    if row is None:
        return "not_found", None
    card_err = await _validate_player_cards(session, owner_user_id, body.player_card_ids)
    if card_err:
        return card_err, None
    existing = [p.player_card_id for p in row.participants]
    merged = existing + [pid for pid in body.player_card_ids if pid not in set(existing)]
    await _replace_participants(session, row, merged)
    await session.commit()
    loaded = await _get_owned_rating(session, owner_user_id, rating_id)
    assert loaded is not None
    return None, _rating_public(loaded)


async def create_rating_game(
    session: AsyncSession,
    owner_user_id: uuid.UUID,
    rating_id: uuid.UUID,
    body: RatingGameWrite,
) -> tuple[str | None, RatingGamePublic | None]:
    row = await _get_owned_rating(session, owner_user_id, rating_id)
    if row is None:
        return "not_found", None
    participant_ids = {p.player_card_id for p in row.participants}
    for result in body.results:
        if result.player_card_id not in participant_ids:
            return "player_not_in_rating", None

    game = RatingGame(
        rating_id=rating_id,
        title=body.title,
        played_at=body.played_at,
        winner_side=body.winner_side,
        source=RatingGameSource.MANUAL,
        lobby_id=None,
    )
    session.add(game)
    await session.flush()
    for index, result in enumerate(body.results):
        session.add(
            RatingGameResult(
                rating_game_id=game.id,
                player_card_id=result.player_card_id,
                role=result.role,
                bonus_points=result.bonus_points,
                total_points=result.total_points,
                best_move=normalize_best_move(result.best_move),
                sort_order=index,
            )
        )
    await session.commit()
    loaded = (
        await session.execute(
            select(RatingGame)
            .where(RatingGame.id == game.id)
            .options(
                selectinload(RatingGame.results).selectinload(RatingGameResult.player_card),
            )
        )
    ).scalar_one()
    return None, _game_public(loaded)


async def sync_rating_from_lobby(
    session: AsyncSession,
    owner_user_id: uuid.UUID,
    rating_id: uuid.UUID,
    body: RatingSyncLobbyBody,
) -> tuple[str | None, RatingGamePublic | None]:
    row = await _get_owned_rating(session, owner_user_id, rating_id)
    if row is None:
        return "rating_not_found", None

    lobby = (
        await session.execute(
            select(GameLobby)
            .where(GameLobby.id == body.lobby_id)
            .options(
                selectinload(GameLobby.member_links).selectinload(
                    LobbyMembership.player_card
                )
            )
        )
    ).scalar_one_or_none()
    if lobby is None:
        return "lobby_not_found", None
    if lobby.host_user_id != owner_user_id:
        return "not_lobby_host", None

    members = sorted(lobby.member_links, key=lambda m: (m.seat_order, m.joined_at))
    if not members:
        return "lobby_empty", None
    if any(member.game_role is None for member in members):
        return "role_not_set", None

    existing_participants = {p.player_card_id for p in row.participants}
    missing_ids = [
        member.player_card_id
        for member in members
        if member.player_card_id not in existing_participants
    ]
    if missing_ids:
        merged = [p.player_card_id for p in row.participants] + missing_ids
        await _replace_participants(session, row, merged)
        await session.flush()

    points_map = {entry.player_card_id: float(entry.total_points) for entry in body.total_points}

    game = RatingGame(
        rating_id=rating_id,
        title=body.title or lobby.title,
        played_at=body.played_at,
        winner_side=body.winner_side,
        source=RatingGameSource.LOBBY_SYNC,
        lobby_id=lobby.id,
    )
    session.add(game)
    await session.flush()

    for index, member in enumerate(members):
        role = member.game_role
        assert role is not None
        bonus = float(member.bonus_points or 0)
        total = float(points_map.get(member.player_card_id, bonus))
        best_move = normalize_best_move(member.best_move)
        session.add(
            RatingGameResult(
                rating_game_id=game.id,
                player_card_id=member.player_card_id,
                role=role,
                bonus_points=bonus,
                total_points=total,
                best_move=best_move,
                sort_order=index,
            )
        )

    await session.commit()
    loaded = (
        await session.execute(
            select(RatingGame)
            .where(RatingGame.id == game.id)
            .options(
                selectinload(RatingGame.results).selectinload(RatingGameResult.player_card),
            )
        )
    ).scalar_one()
    return None, _game_public(loaded)


async def get_rating_table(
    session: AsyncSession, owner_user_id: uuid.UUID, rating_id: uuid.UUID
) -> tuple[str | None, RatingTableResponse | None]:
    row = await _get_owned_rating(session, owner_user_id, rating_id, with_games=True)
    if row is None:
        return "not_found", None

    by_player: dict[uuid.UUID, RatingTableRow] = {}
    for participant in row.participants:
        card = participant.player_card
        photo_url: str | None = None
        if card.photo_urls:
            first = card.photo_urls[0]
            if isinstance(first, str) and first.strip():
                photo_url = first.strip()
        by_player[participant.player_card_id] = RatingTableRow(
            player_card_id=participant.player_card_id,
            nickname=card.nickname,
            first_name=card.first_name,
            last_name=card.last_name,
            club=card.club,
            photo_url=photo_url,
        )

    for game in row.games:
        for result in game.results:
            table_row = by_player.get(result.player_card_id)
            if table_row is None:
                continue
            role = result.role
            table_row.games_total += 1
            if role in _BLACK_ROLES:
                table_row.games_black += 1
            if role in _RED_ROLES:
                table_row.games_red += 1
            if role == GameRole.MAFIA:
                table_row.games_mafia += 1
            if role == GameRole.PEACEFUL:
                table_row.games_peaceful += 1
            if role == GameRole.SHERIFF:
                table_row.games_sheriff += 1
            if role == GameRole.DON:
                table_row.games_don += 1

            won = (
                (game.winner_side == RatingWinnerSide.BLACK and role in _BLACK_ROLES)
                or (game.winner_side == RatingWinnerSide.RED and role in _RED_ROLES)
            )
            if won:
                table_row.wins_total += 1

            bonus = float(result.bonus_points)
            table_row.bonus_points_sum = round(table_row.bonus_points_sum + bonus, 1)
            hits = count_correct_mafia_hits(result.best_move, game.results)
            if has_best_move(result.best_move):
                # По продуктовой логике это счетчик "сколько раз игроку выдали ЛХ".
                table_row.best_move_sum = round(table_row.best_move_sum + 1, 1)
                if hits == 0:
                    table_row.best_move_count_0 += 1
                elif hits == 1:
                    table_row.best_move_count_1 += 1
                elif hits == 2:
                    table_row.best_move_count_2 += 1
                else:
                    table_row.best_move_count_3 += 1
            if bonus > 0:
                table_row.bonus_points_plus_sum = round(
                    table_row.bonus_points_plus_sum + bonus, 1
                )
                if role == GameRole.PEACEFUL:
                    table_row.bonus_peaceful_plus_sum = round(
                        table_row.bonus_peaceful_plus_sum + bonus, 1
                    )
                elif role == GameRole.MAFIA:
                    table_row.bonus_mafia_plus_sum = round(
                        table_row.bonus_mafia_plus_sum + bonus, 1
                    )
                elif role == GameRole.DON:
                    table_row.bonus_don_plus_sum = round(
                        table_row.bonus_don_plus_sum + bonus, 1
                    )
                elif role == GameRole.SHERIFF:
                    table_row.bonus_sheriff_plus_sum = round(
                        table_row.bonus_sheriff_plus_sum + bonus, 1
                    )
            elif bonus < 0:
                bonus_abs = abs(bonus)
                table_row.bonus_points_minus_sum = round(
                    table_row.bonus_points_minus_sum + bonus_abs, 1
                )
                if role == GameRole.PEACEFUL:
                    table_row.bonus_peaceful_minus_sum = round(
                        table_row.bonus_peaceful_minus_sum + bonus_abs, 1
                    )
                elif role == GameRole.MAFIA:
                    table_row.bonus_mafia_minus_sum = round(
                        table_row.bonus_mafia_minus_sum + bonus_abs, 1
                    )
                elif role == GameRole.DON:
                    table_row.bonus_don_minus_sum = round(
                        table_row.bonus_don_minus_sum + bonus_abs, 1
                    )
                elif role == GameRole.SHERIFF:
                    table_row.bonus_sheriff_minus_sum = round(
                        table_row.bonus_sheriff_minus_sum + bonus_abs, 1
                    )
            table_row.total_points_sum = round(
                table_row.total_points_sum + float(result.total_points), 1
            )
            if role == GameRole.MAFIA:
                table_row.total_points_mafia_sum = round(
                    table_row.total_points_mafia_sum + float(result.total_points), 1
                )
            elif role == GameRole.PEACEFUL:
                table_row.total_points_peaceful_sum = round(
                    table_row.total_points_peaceful_sum + float(result.total_points), 1
                )
            elif role == GameRole.SHERIFF:
                table_row.total_points_sheriff_sum = round(
                    table_row.total_points_sheriff_sum + float(result.total_points), 1
                )
            elif role == GameRole.DON:
                table_row.total_points_don_sum = round(
                    table_row.total_points_don_sum + float(result.total_points), 1
                )

    for table_row in by_player.values():
        if table_row.games_mafia > 0:
            table_row.avg_points_mafia = round(
                table_row.total_points_mafia_sum / table_row.games_mafia, 2
            )
        if table_row.games_peaceful > 0:
            table_row.avg_points_peaceful = round(
                table_row.total_points_peaceful_sum / table_row.games_peaceful, 2
            )
        if table_row.games_sheriff > 0:
            table_row.avg_points_sheriff = round(
                table_row.total_points_sheriff_sum / table_row.games_sheriff, 2
            )
        if table_row.games_don > 0:
            table_row.avg_points_don = round(table_row.total_points_don_sum / table_row.games_don, 2)

        table_row.games_count = table_row.games_total
        table_row.black_games_count = table_row.games_black
        table_row.red_games_count = table_row.games_red
        table_row.games_as_black = table_row.games_black
        table_row.games_as_red = table_row.games_red
        table_row.sheriff_games_count = table_row.games_sheriff
        table_row.don_games_count = table_row.games_don
        table_row.games_as_sheriff = table_row.games_sheriff
        table_row.games_as_don = table_row.games_don
        table_row.mafia_games_count = table_row.games_mafia
        table_row.peaceful_games_count = table_row.games_peaceful
        table_row.games_as_mafia = table_row.games_mafia
        table_row.games_as_peaceful = table_row.games_peaceful
        table_row.bonus_peaceful_plus_total = table_row.bonus_peaceful_plus_sum
        table_row.bonus_peaceful_minus_total = table_row.bonus_peaceful_minus_sum
        table_row.bonus_mafia_plus_total = table_row.bonus_mafia_plus_sum
        table_row.bonus_mafia_minus_total = table_row.bonus_mafia_minus_sum
        table_row.bonus_don_plus_total = table_row.bonus_don_plus_sum
        table_row.bonus_don_minus_total = table_row.bonus_don_minus_sum
        table_row.bonus_sheriff_plus_total = table_row.bonus_sheriff_plus_sum
        table_row.bonus_sheriff_minus_total = table_row.bonus_sheriff_minus_sum
        table_row.bonus_points_plus_total = table_row.bonus_points_plus_sum
        table_row.bonus_points_minus_total = table_row.bonus_points_minus_sum
        table_row.bonus_points_total = table_row.bonus_points_sum
        table_row.total_points_total = table_row.total_points_sum

    ordered_rows = sorted(by_player.values(), key=lambda x: x.total_points_sum, reverse=True)
    _assign_role_award_flags(ordered_rows)
    return None, RatingTableResponse(rating_id=rating_id, rows=ordered_rows)


async def delete_rating(
    session: AsyncSession, owner_user_id: uuid.UUID, rating_id: uuid.UUID
) -> tuple[str | None, bool]:
    row = await _get_owned_rating(session, owner_user_id, rating_id)
    if row is None:
        return "not_found", False
    await session.delete(row)
    await session.commit()
    return None, True
