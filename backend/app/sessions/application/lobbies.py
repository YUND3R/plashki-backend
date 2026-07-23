import uuid

from sqlalchemy import and_, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.commerce.application.contracts import OverlayDesignOption
from app.commerce.application.overlay_designs import SqlAlchemyOverlayDesignAccess
from app.db.models import (
    BroadcastUserSettings,
    GameLobby,
    LobbyMembership,
    PlayerCard,
    UserProfile,
)
from app.schemas.list_filters import LobbyListFilters
from app.schemas.lobby import (
    GameLobbyPublic,
    ImportedLobbyState,
    ImportedLobbyVariant,
    ImportedTournamentParticipant,
    ImportedTournamentParticipantsResponse,
    LobbyOverlayDesignOption,
    LobbyPlayerPublic,
)


def _option_response(option: OverlayDesignOption) -> LobbyOverlayDesignOption:
    return LobbyOverlayDesignOption(
        code=option.code,
        title=option.title,
        price_rub=option.price_rub,
        rental_hours=option.rental_hours,
        animations_supported=option.animations_supported,
        selectable=option.selectable,
        access_expires_at=option.access_expires_at,
        access_unlimited=option.access_unlimited,
    )


async def design_catalog(
    session: AsyncSession, user_id: uuid.UUID | None
) -> list[LobbyOverlayDesignOption]:
    options = await SqlAlchemyOverlayDesignAccess(session).options_for_user(user_id)
    return [_option_response(option) for option in options]


def build_imported_state(lobby: GameLobby) -> ImportedLobbyState | None:
    source_url = (lobby.imported_source_url or "").strip()
    current_key = (lobby.imported_current_key or "").strip()
    raw_variants = lobby.imported_variants or []
    if not source_url or not current_key or not raw_variants:
        return None
    variants: list[ImportedLobbyVariant] = []
    for raw in raw_variants:
        if not isinstance(raw, dict):
            continue
        try:
            variant = ImportedLobbyVariant(
                key=str(raw.get("key", "")).strip(),
                title=str(raw.get("title", "")).strip(),
                tour_no=int(raw.get("tour_no", 0)),
                table_label=str(raw.get("table_label", "")).strip(),
                players_count=max(int(raw.get("players_count", 0)), 0),
            )
        except (TypeError, ValueError):
            continue
        if variant.key and variant.title and variant.tour_no > 0:
            variants.append(variant)
    if not variants:
        return None
    if current_key not in {variant.key for variant in variants}:
        current_key = variants[0].key
    return ImportedLobbyState(
        source_url=source_url, current_key=current_key, variants=variants
    )


def _is_imported_lobby_expr():
    return and_(
        GameLobby.imported_source_url.isnot(None),
        func.length(func.btrim(GameLobby.imported_source_url)) > 0,
    )


def _apply_filters(stmt, filters: LobbyListFilters):
    if filters.source == "created":
        return stmt.where(~_is_imported_lobby_expr())
    if filters.source == "imported":
        return stmt.where(_is_imported_lobby_expr())
    return stmt


async def count_game_lobbies(
    session: AsyncSession,
    host_user_id: uuid.UUID | None = None,
    *,
    filters: LobbyListFilters | None = None,
) -> int:
    stmt = select(func.count()).select_from(GameLobby)
    if host_user_id is not None:
        stmt = stmt.where(GameLobby.host_user_id == host_user_id)
    if filters is not None:
        stmt = _apply_filters(stmt, filters)
    return int((await session.execute(stmt)).scalar_one())


def _player_response(membership: LobbyMembership) -> LobbyPlayerPublic:
    card = membership.player_card
    return LobbyPlayerPublic(
        membership_id=membership.id,
        player_card_id=card.id,
        user_id=card.owner.id,
        username=card.owner.username,
        nickname=card.nickname,
        lobby_photo_url=membership.lobby_photo_url,
        photo_urls=list(card.photo_urls),
        game_role=membership.game_role.value if membership.game_role else None,
        status=membership.status.value if membership.status else None,
        best_move=list(membership.best_move or []),
        bonus_points=membership.bonus_points,
        joined_at=membership.joined_at,
    )


async def _public_lobby(
    session: AsyncSession,
    lobby: GameLobby,
    *,
    catalog: list[LobbyOverlayDesignOption] | None = None,
) -> GameLobbyPublic:
    members = sorted(lobby.member_links, key=lambda m: (m.seat_order, m.joined_at))
    return GameLobbyPublic(
        id=lobby.id,
        overlay_public_id=lobby.overlay_public_id,
        max_players=lobby.max_players,
        title=lobby.title,
        host_user_id=lobby.host_user_id,
        selected_overlay_design=lobby.selected_overlay_design.value,
        active_overlay_screen=lobby.active_overlay_screen,
        show_victory_scores=lobby.show_victory_scores,
        design_catalog=catalog
        if catalog is not None
        else await design_catalog(session, lobby.host_user_id),
        sheriff_check=list(lobby.sheriff_check or []),
        best_move=list(lobby.best_move or []),
        imported_state=build_imported_state(lobby),
        created_at=lobby.created_at,
        players=[_player_response(member) for member in members],
    )


def _lobby_query():
    return select(GameLobby).options(
        selectinload(GameLobby.member_links)
        .selectinload(LobbyMembership.player_card)
        .selectinload(PlayerCard.owner)
    )


async def list_lobbies_for_host(
    session: AsyncSession,
    host_user_id: uuid.UUID,
    *,
    filters: LobbyListFilters | None = None,
) -> list[GameLobbyPublic]:
    stmt = _apply_filters(
        _lobby_query().where(GameLobby.host_user_id == host_user_id),
        filters or LobbyListFilters(),
    ).order_by(GameLobby.created_at.desc())
    lobbies = (await session.execute(stmt)).scalars().all()
    catalog = await design_catalog(session, host_user_id)
    return [await _public_lobby(session, lobby, catalog=catalog) for lobby in lobbies]


async def get_lobby_with_players(
    session: AsyncSession,
    lobby_id: uuid.UUID,
    viewer_user_id: uuid.UUID | None = None,
) -> GameLobbyPublic | None:
    lobby = (
        await session.execute(_lobby_query().where(GameLobby.id == lobby_id))
    ).scalar_one_or_none()
    if lobby is None or (
        viewer_user_id is not None and lobby.host_user_id != viewer_user_id
    ):
        return None
    return await _public_lobby(session, lobby)


async def create_lobby(
    session: AsyncSession,
    max_players: int,
    host_user_id: uuid.UUID,
    title: str,
) -> tuple[str | None, GameLobbyPublic | None]:
    if await session.get(UserProfile, host_user_id) is None:
        return "host_not_found", None
    lobby = GameLobby(
        max_players=max_players,
        host_user_id=host_user_id,
        title=title.strip() or "Лобби",
    )
    session.add(lobby)
    await session.commit()
    await session.refresh(lobby)
    return None, await get_lobby_with_players(session, lobby.id)


async def delete_lobby(
    session: AsyncSession, lobby_id: uuid.UUID, acting_user_id: uuid.UUID
) -> str | None:
    lobby = await session.get(GameLobby, lobby_id)
    if lobby is None:
        return "lobby_not_found"
    if lobby.host_user_id is None or lobby.host_user_id != acting_user_id:
        return "not_host"
    await session.execute(
        update(BroadcastUserSettings)
        .where(BroadcastUserSettings.active_overlay_lobby_id == lobby_id)
        .values(active_overlay_lobby_id=None)
    )
    await session.delete(lobby)
    await session.commit()
    return None


async def require_lobby_host(
    session: AsyncSession, lobby_id: uuid.UUID, acting_user_id: uuid.UUID
) -> tuple[str | None, GameLobby | None]:
    lobby = await session.get(GameLobby, lobby_id)
    if lobby is None:
        return "lobby_not_found", None
    if lobby.host_user_id is None or lobby.host_user_id != acting_user_id:
        return "not_host", None
    return None, lobby


async def select_imported_lobby_variant(
    session: AsyncSession,
    lobby_id: uuid.UUID,
    variant_key: str,
    acting_user_id: uuid.UUID,
) -> tuple[str | None, GameLobbyPublic | None]:
    err, lobby = await require_lobby_host(session, lobby_id, acting_user_id)
    if err or lobby is None:
        return err, None
    if not lobby.imported_variants:
        return "not_imported_lobby", None
    key = variant_key.strip()
    selected = next(
        (
            raw
            for raw in lobby.imported_variants
            if isinstance(raw, dict) and str(raw.get("key", "")).strip() == key
        ),
        None,
    )
    if selected is None:
        return "variant_not_found", None
    raw_seats = selected.get("seats")
    if not isinstance(raw_seats, list) or not raw_seats:
        return "variant_invalid", None
    memberships: list[LobbyMembership] = []
    try:
        for seat in raw_seats:
            if not isinstance(seat, dict):
                raise ValueError
            memberships.append(
                LobbyMembership(
                    lobby_id=lobby_id,
                    player_card_id=uuid.UUID(str(seat["player_card_id"])),
                    seat_order=int(seat["seat_order"]),
                )
            )
    except (KeyError, TypeError, ValueError):
        return "variant_invalid", None
    await session.execute(
        delete(LobbyMembership).where(LobbyMembership.lobby_id == lobby_id)
    )
    lobby.imported_current_key = key
    session.add_all(memberships)
    await session.commit()
    return None, await get_lobby_with_players(session, lobby_id, acting_user_id)


async def list_imported_tournament_participants(
    session: AsyncSession, lobby_id: uuid.UUID, viewer_user_id: uuid.UUID
) -> tuple[str | None, ImportedTournamentParticipantsResponse | None]:
    err, lobby = await require_lobby_host(session, lobby_id, viewer_user_id)
    if err or lobby is None:
        return err, None
    source_url = (lobby.imported_source_url or "").strip()
    if not source_url or not lobby.imported_variants:
        return "not_imported_lobby", None
    participants: dict[uuid.UUID, ImportedTournamentParticipant] = {}
    for variant in lobby.imported_variants:
        seats = variant.get("seats") if isinstance(variant, dict) else None
        if not isinstance(seats, list):
            continue
        for seat in seats:
            if not isinstance(seat, dict):
                continue
            nickname = str(seat.get("nickname", "")).strip()
            try:
                card_id = uuid.UUID(str(seat.get("player_card_id", "")))
            except ValueError:
                continue
            if nickname:
                participants.setdefault(
                    card_id,
                    ImportedTournamentParticipant(
                        player_card_id=card_id, nickname=nickname
                    ),
                )
    ordered = sorted(
        participants.values(), key=lambda item: (item.nickname.lower(), str(item.player_card_id))
    )
    return None, ImportedTournamentParticipantsResponse(
        lobby_id=lobby.id, source_url=source_url, participants=ordered
    )
