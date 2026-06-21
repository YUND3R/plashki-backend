import uuid

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.base import GameRole, GameStatus, OverlayDesign, Subscription
from app.db.models import GameLobby, LobbyMembership, PlayerCard, UserProfile
from app.schemas.lobby import (
    GameLobbyPublic,
    ImportedTournamentParticipant,
    ImportedTournamentParticipantsResponse,
    ImportedLobbyState,
    ImportedLobbyVariant,
    OverlayDesignCatalogResponse,
    LobbyOverlayDesignOption,
    LobbyOverlayDesignsResponse,
    LobbyPlayerPublic,
    LobbyOverlayStateResponse,
    OverlayPlayerState,
)


_SUBSCRIPTION_ORDER: dict[Subscription, int] = {
    Subscription.FREE: 0,
    Subscription.STANDARD: 1,
    Subscription.PREMIUM: 2,
}

_OVERLAY_DESIGN_CATALOG: dict[OverlayDesign, dict[str, object]] = {
    OverlayDesign.MASTERS_YUG25: {
        "title": "Мастерс ЮГ25",
        "required_subscription": Subscription.FREE,
        "animations_supported": True,
    },
    OverlayDesign.CLASSIC: {
        "title": "Classic",
        "required_subscription": Subscription.FREE,
        "animations_supported": True,
    },
    OverlayDesign.PLUS: {
        "title": "Plus",
        "required_subscription": Subscription.FREE,
        "animations_supported": True,
    },
}


def _build_design_options(host_subscription: Subscription) -> list[LobbyOverlayDesignOption]:
    options: list[LobbyOverlayDesignOption] = []
    for code, raw in _OVERLAY_DESIGN_CATALOG.items():
        required_subscription = raw["required_subscription"]
        assert isinstance(required_subscription, Subscription)
        animations_supported = bool(raw["animations_supported"])
        options.append(
            LobbyOverlayDesignOption(
                code=code,
                title=str(raw["title"]),
                required_subscription=required_subscription,
                animations_supported=animations_supported,
                selectable=_has_subscription_access(host_subscription, required_subscription),
            )
        )
    return options


def _build_imported_state(lobby: GameLobby) -> ImportedLobbyState | None:
    source_url = (lobby.imported_source_url or "").strip()
    current_key = (lobby.imported_current_key or "").strip()
    raw_variants = lobby.imported_variants or []
    if not source_url or not current_key or not raw_variants:
        return None
    variants: list[ImportedLobbyVariant] = []
    for raw in raw_variants:
        if not isinstance(raw, dict):
            continue
        key = str(raw.get("key", "")).strip()
        title = str(raw.get("title", "")).strip()
        table_label = str(raw.get("table_label", "")).strip()
        try:
            tour_no = int(raw.get("tour_no", 0))
            players_count = int(raw.get("players_count", 0))
        except (TypeError, ValueError):
            continue
        if not key or not title or tour_no <= 0:
            continue
        variants.append(
            ImportedLobbyVariant(
                key=key,
                title=title,
                tour_no=tour_no,
                table_label=table_label,
                players_count=max(players_count, 0),
            )
        )
    if not variants:
        return None
    valid_keys = {v.key for v in variants}
    if current_key not in valid_keys:
        current_key = variants[0].key
    return ImportedLobbyState(
        source_url=source_url,
        current_key=current_key,
        variants=variants,
    )


async def count_game_lobbies(
    session: AsyncSession,
    host_user_id: uuid.UUID | None = None,
) -> int:
    stmt = select(func.count()).select_from(GameLobby)
    if host_user_id is not None:
        stmt = stmt.where(GameLobby.host_user_id == host_user_id)
    return int((await session.execute(stmt)).scalar_one())


async def list_lobbies_for_host(
    session: AsyncSession,
    host_user_id: uuid.UUID,
) -> list[GameLobbyPublic]:
    stmt = (
        select(GameLobby)
        .where(GameLobby.host_user_id == host_user_id)
        .order_by(GameLobby.created_at.desc())
        .options(
            selectinload(GameLobby.member_links)
            .selectinload(LobbyMembership.player_card)
            .selectinload(PlayerCard.owner),
        )
    )
    lobbies = (await session.execute(stmt)).scalars().all()
    host = await session.get(UserProfile, host_user_id)
    host_subscription = host.subscription if host else Subscription.FREE

    out: list[GameLobbyPublic] = []
    for lobby in lobbies:
        members = sorted(lobby.member_links, key=lambda m: (m.seat_order, m.joined_at))
        players: list[LobbyPlayerPublic] = []
        for m in members:
            card = m.player_card
            owner = card.owner
            players.append(
                LobbyPlayerPublic(
                    membership_id=m.id,
                    player_card_id=card.id,
                    user_id=owner.id,
                    username=owner.username,
                    nickname=card.nickname,
                    lobby_photo_url=m.lobby_photo_url,
                    photo_urls=list(card.photo_urls),
                    game_role=m.game_role.value if m.game_role else None,
                    status=m.status.value if m.status else None,
                    joined_at=m.joined_at,
                )
            )
        out.append(
            GameLobbyPublic(
                id=lobby.id,
                overlay_public_id=lobby.overlay_public_id,
                max_players=lobby.max_players,
                title=lobby.title,
                host_user_id=lobby.host_user_id,
                selected_overlay_design=lobby.selected_overlay_design.value,
                design_catalog=_build_design_options(host_subscription),
                sheriff_check=list(lobby.sheriff_check or []),
                best_move=list(lobby.best_move or []),
                imported_state=_build_imported_state(lobby),
                created_at=lobby.created_at,
                players=players,
            )
        )
    return out


async def get_lobby_with_players(
    session: AsyncSession,
    lobby_id: uuid.UUID,
    viewer_user_id: uuid.UUID | None = None,
) -> GameLobbyPublic | None:
    stmt = (
        select(GameLobby)
        .where(GameLobby.id == lobby_id)
        .options(
            selectinload(GameLobby.member_links)
            .selectinload(LobbyMembership.player_card)
            .selectinload(PlayerCard.owner),
        )
    )
    result = await session.execute(stmt)
    lobby = result.scalar_one_or_none()
    if lobby is None:
        return None
    if viewer_user_id is not None and lobby.host_user_id != viewer_user_id:
        return None
    host = await session.get(UserProfile, lobby.host_user_id) if lobby.host_user_id else None
    host_subscription = host.subscription if host else Subscription.FREE
    members = sorted(lobby.member_links, key=lambda m: (m.seat_order, m.joined_at))
    players = []
    for m in members:
        card = m.player_card
        owner = card.owner
        players.append(
            LobbyPlayerPublic(
                membership_id=m.id,
                player_card_id=card.id,
                user_id=owner.id,
                username=owner.username,
                nickname=card.nickname,
                lobby_photo_url=m.lobby_photo_url,
                photo_urls=list(card.photo_urls),
                game_role=m.game_role.value if m.game_role else None,
                status=m.status.value if m.status else None,
                joined_at=m.joined_at,
            )
        )
    return GameLobbyPublic(
        id=lobby.id,
        overlay_public_id=lobby.overlay_public_id,
        max_players=lobby.max_players,
        title=lobby.title,
        host_user_id=lobby.host_user_id,
        selected_overlay_design=lobby.selected_overlay_design.value,
        design_catalog=_build_design_options(host_subscription),
        sheriff_check=list(lobby.sheriff_check or []),
        best_move=list(lobby.best_move or []),
        imported_state=_build_imported_state(lobby),
        created_at=lobby.created_at,
        players=players,
    )


async def create_lobby(
    session: AsyncSession,
    max_players: int,
    host_user_id: uuid.UUID,
    title: str,
) -> tuple[str | None, GameLobbyPublic | None]:
    host = await session.get(UserProfile, host_user_id)
    if host is None:
        return "host_not_found", None
    lobby = GameLobby(
        max_players=max_players,
        host_user_id=host_user_id,
        title=title.strip() or "Лобби",
    )
    session.add(lobby)
    await session.commit()
    await session.refresh(lobby)
    return None, GameLobbyPublic(
        id=lobby.id,
        overlay_public_id=lobby.overlay_public_id,
        max_players=lobby.max_players,
        title=lobby.title,
        host_user_id=lobby.host_user_id,
        selected_overlay_design=lobby.selected_overlay_design.value,
        design_catalog=_build_design_options(host.subscription),
        sheriff_check=list(lobby.sheriff_check or []),
        best_move=list(lobby.best_move or []),
        imported_state=_build_imported_state(lobby),
        created_at=lobby.created_at,
        players=[],
    )


async def delete_lobby(
    session: AsyncSession,
    lobby_id: uuid.UUID,
    acting_user_id: uuid.UUID,
) -> str | None:
    lobby = await session.get(GameLobby, lobby_id)
    if lobby is None:
        return "lobby_not_found"
    if lobby.host_user_id is None or lobby.host_user_id != acting_user_id:
        return "not_host"
    await session.delete(lobby)
    await session.commit()
    return None


async def select_imported_lobby_variant(
    session: AsyncSession,
    lobby_id: uuid.UUID,
    variant_key: str,
    acting_user_id: uuid.UUID,
) -> tuple[str | None, GameLobbyPublic | None]:
    lobby = await session.get(GameLobby, lobby_id)
    if lobby is None:
        return "lobby_not_found", None
    if lobby.host_user_id is None or lobby.host_user_id != acting_user_id:
        return "not_host", None
    if not lobby.imported_variants:
        return "not_imported_lobby", None

    target_key = variant_key.strip()
    selected_variant: dict | None = None
    for raw in lobby.imported_variants:
        if isinstance(raw, dict) and str(raw.get("key", "")).strip() == target_key:
            selected_variant = raw
            break
    if selected_variant is None:
        return "variant_not_found", None

    raw_seats = selected_variant.get("seats")
    if not isinstance(raw_seats, list) or not raw_seats:
        return "variant_invalid", None

    new_memberships: list[LobbyMembership] = []
    for raw_seat in raw_seats:
        if not isinstance(raw_seat, dict):
            return "variant_invalid", None
        try:
            seat_order = int(raw_seat["seat_order"])
            player_card_id = uuid.UUID(str(raw_seat["player_card_id"]))
        except (KeyError, TypeError, ValueError):
            return "variant_invalid", None
        new_memberships.append(
            LobbyMembership(
                lobby_id=lobby_id,
                player_card_id=player_card_id,
                seat_order=seat_order,
            )
        )

    await session.execute(delete(LobbyMembership).where(LobbyMembership.lobby_id == lobby_id))
    lobby.imported_current_key = target_key
    session.add_all(new_memberships)
    await session.commit()
    return None, await get_lobby_with_players(session, lobby_id, viewer_user_id=acting_user_id)


async def list_imported_tournament_participants(
    session: AsyncSession,
    lobby_id: uuid.UUID,
    viewer_user_id: uuid.UUID,
) -> tuple[str | None, ImportedTournamentParticipantsResponse | None]:
    lobby = await session.get(GameLobby, lobby_id)
    if lobby is None:
        return "lobby_not_found", None
    if lobby.host_user_id is None or lobby.host_user_id != viewer_user_id:
        return "not_host", None
    if not lobby.imported_variants:
        return "not_imported_lobby", None

    source_url = (lobby.imported_source_url or "").strip()
    if not source_url:
        return "not_imported_lobby", None

    participants_by_card_id: dict[uuid.UUID, ImportedTournamentParticipant] = {}
    for raw_variant in lobby.imported_variants:
        if not isinstance(raw_variant, dict):
            continue
        raw_seats = raw_variant.get("seats")
        if not isinstance(raw_seats, list):
            continue
        for raw_seat in raw_seats:
            if not isinstance(raw_seat, dict):
                continue
            raw_nickname = str(raw_seat.get("nickname", "")).strip()
            raw_card_id = str(raw_seat.get("player_card_id", "")).strip()
            if not raw_nickname or not raw_card_id:
                continue
            try:
                card_id = uuid.UUID(raw_card_id)
            except ValueError:
                continue
            if card_id in participants_by_card_id:
                continue
            participants_by_card_id[card_id] = ImportedTournamentParticipant(
                player_card_id=card_id,
                nickname=raw_nickname,
            )

    participants = sorted(
        participants_by_card_id.values(),
        key=lambda p: (p.nickname.lower(), str(p.player_card_id)),
    )
    return (
        None,
        ImportedTournamentParticipantsResponse(
            lobby_id=lobby.id,
            source_url=source_url,
            participants=participants,
        ),
    )


def _has_subscription_access(user_subscription: Subscription, required: Subscription) -> bool:
    return _SUBSCRIPTION_ORDER[user_subscription] >= _SUBSCRIPTION_ORDER[required]


async def _require_lobby_host(
    session: AsyncSession,
    lobby_id: uuid.UUID,
    acting_user_id: uuid.UUID,
) -> tuple[str | None, GameLobby | None]:
    lobby = await session.get(GameLobby, lobby_id)
    if lobby is None:
        return "lobby_not_found", None
    if lobby.host_user_id is None or lobby.host_user_id != acting_user_id:
        return "not_host", None
    return None, lobby


async def get_overlay_design_options(
    session: AsyncSession,
    lobby_id: uuid.UUID,
    viewer_user_id: uuid.UUID | None = None,
) -> LobbyOverlayDesignsResponse | None:
    lobby = await session.get(GameLobby, lobby_id)
    if lobby is None:
        return None
    if viewer_user_id is not None and lobby.host_user_id != viewer_user_id:
        return None
    host = await session.get(UserProfile, lobby.host_user_id) if lobby.host_user_id else None
    host_subscription = host.subscription if host else Subscription.FREE
    return LobbyOverlayDesignsResponse(
        lobby_id=lobby.id,
        selected_overlay_design=lobby.selected_overlay_design,
        options=_build_design_options(host_subscription),
    )


async def get_overlay_design_catalog_for_user(
    session: AsyncSession,
    user_id: uuid.UUID,
) -> OverlayDesignCatalogResponse | None:
    user = await session.get(UserProfile, user_id)
    if user is None:
        return None
    return OverlayDesignCatalogResponse(options=_build_design_options(user.subscription))


async def set_lobby_overlay_design(
    session: AsyncSession,
    lobby_id: uuid.UUID,
    overlay_design: OverlayDesign,
    acting_user_id: uuid.UUID,
) -> tuple[str | None, GameLobbyPublic | None]:
    lobby = await session.get(GameLobby, lobby_id)
    if lobby is None:
        return "lobby_not_found", None
    if lobby.host_user_id is None or lobby.host_user_id != acting_user_id:
        return "not_host", None

    host = await session.get(UserProfile, acting_user_id)
    if host is None:
        return "host_not_found", None

    raw = _OVERLAY_DESIGN_CATALOG.get(overlay_design)
    if raw is None:
        return "unknown_design", None
    required_subscription = raw["required_subscription"]
    assert isinstance(required_subscription, Subscription)
    if not _has_subscription_access(host.subscription, required_subscription):
        return "subscription_required", None

    lobby.selected_overlay_design = overlay_design
    await session.commit()
    return None, await get_lobby_with_players(session, lobby_id)


async def get_lobby_overlay_state(
    session: AsyncSession,
    lobby_id: uuid.UUID,
    viewer_user_id: uuid.UUID | None = None,
) -> LobbyOverlayStateResponse | None:
    stmt = (
        select(GameLobby)
        .where(GameLobby.id == lobby_id)
        .options(
            selectinload(GameLobby.member_links).selectinload(LobbyMembership.player_card),
        )
    )
    result = await session.execute(stmt)
    lobby = result.scalar_one_or_none()
    if lobby is None:
        return None
    if viewer_user_id is not None and lobby.host_user_id != viewer_user_id:
        return None
    host = await session.get(UserProfile, lobby.host_user_id) if lobby.host_user_id else None
    host_subscription = host.subscription if host else Subscription.FREE

    members = sorted(lobby.member_links, key=lambda m: (m.seat_order, m.joined_at))
    players: list[OverlayPlayerState] = []
    for m in members:
        players.append(
            OverlayPlayerState(
                seat_order=m.seat_order,
                membership_id=m.id,
                nickname=m.player_card.nickname,
                lobby_photo_url=m.lobby_photo_url,
                game_role=m.game_role.value if m.game_role else None,
                status=m.status.value if m.status else None,
            )
        )

    return LobbyOverlayStateResponse(
        lobby_id=lobby.id,
        selected_overlay_design=lobby.selected_overlay_design,
        design_catalog=_build_design_options(host_subscription),
        sheriff_check=list(lobby.sheriff_check or []),
        best_move=list(lobby.best_move or []),
        players=players,
    )


async def get_lobby_overlay_state_by_public_id(
    session: AsyncSession,
    overlay_public_id: uuid.UUID,
    expected_lobby_id: uuid.UUID | None = None,
) -> LobbyOverlayStateResponse | None:
    stmt = select(GameLobby).where(GameLobby.overlay_public_id == overlay_public_id)
    if expected_lobby_id is not None:
        stmt = stmt.where(GameLobby.id == expected_lobby_id)
    stmt = stmt.options(
        selectinload(GameLobby.member_links).selectinload(LobbyMembership.player_card),
    )
    result = await session.execute(stmt)
    lobby = result.scalar_one_or_none()
    if lobby is None:
        return None
    host = await session.get(UserProfile, lobby.host_user_id) if lobby.host_user_id else None
    host_subscription = host.subscription if host else Subscription.FREE

    members = sorted(lobby.member_links, key=lambda m: (m.seat_order, m.joined_at))
    players: list[OverlayPlayerState] = []
    for m in members:
        players.append(
            OverlayPlayerState(
                seat_order=m.seat_order,
                membership_id=m.id,
                nickname=m.player_card.nickname,
                lobby_photo_url=m.lobby_photo_url,
                game_role=m.game_role.value if m.game_role else None,
                status=m.status.value if m.status else None,
            )
        )

    return LobbyOverlayStateResponse(
        lobby_id=lobby.id,
        selected_overlay_design=lobby.selected_overlay_design,
        design_catalog=_build_design_options(host_subscription),
        sheriff_check=list(lobby.sheriff_check or []),
        best_move=list(lobby.best_move or []),
        players=players,
    )


async def set_lobby_sheriff_check(
    session: AsyncSession,
    lobby_id: uuid.UUID,
    sheriff_check: list[str],
    acting_user_id: uuid.UUID,
) -> tuple[str | None, GameLobbyPublic | None]:
    lobby = await session.get(GameLobby, lobby_id)
    if lobby is None:
        return "lobby_not_found", None
    if lobby.host_user_id is None or lobby.host_user_id != acting_user_id:
        return "not_host", None
    lobby.sheriff_check = list(sheriff_check)
    await session.commit()
    return None, await get_lobby_with_players(session, lobby_id)


async def clear_lobby_sheriff_check(
    session: AsyncSession,
    lobby_id: uuid.UUID,
    acting_user_id: uuid.UUID,
) -> tuple[str | None, GameLobbyPublic | None]:
    lobby = await session.get(GameLobby, lobby_id)
    if lobby is None:
        return "lobby_not_found", None
    if lobby.host_user_id is None or lobby.host_user_id != acting_user_id:
        return "not_host", None
    lobby.sheriff_check = []
    await session.commit()
    return None, await get_lobby_with_players(session, lobby_id)


async def set_lobby_best_move(
    session: AsyncSession,
    lobby_id: uuid.UUID,
    best_move: list[str],
    acting_user_id: uuid.UUID,
) -> tuple[str | None, GameLobbyPublic | None]:
    lobby = await session.get(GameLobby, lobby_id)
    if lobby is None:
        return "lobby_not_found", None
    if lobby.host_user_id is None or lobby.host_user_id != acting_user_id:
        return "not_host", None
    lobby.best_move = list(best_move)
    await session.commit()
    return None, await get_lobby_with_players(session, lobby_id)


async def clear_lobby_best_move(
    session: AsyncSession,
    lobby_id: uuid.UUID,
    acting_user_id: uuid.UUID,
) -> tuple[str | None, GameLobbyPublic | None]:
    lobby = await session.get(GameLobby, lobby_id)
    if lobby is None:
        return "lobby_not_found", None
    if lobby.host_user_id is None or lobby.host_user_id != acting_user_id:
        return "not_host", None
    lobby.best_move = []
    await session.commit()
    return None, await get_lobby_with_players(session, lobby_id)


async def add_card_to_lobby(
    session: AsyncSession,
    lobby_id: uuid.UUID,
    player_card_id: uuid.UUID,
    acting_user_id: uuid.UUID,
) -> tuple[str | None, GameLobbyPublic | None]:
    stmt = (
        select(GameLobby)
        .where(GameLobby.id == lobby_id)
        .options(selectinload(GameLobby.member_links))
    )
    result = await session.execute(stmt)
    lobby = result.scalar_one_or_none()
    if lobby is None:
        return "lobby_not_found", None

    card = await session.get(PlayerCard, player_card_id)
    if card is None:
        return "card_not_found", None
    if card.owner_user_id != acting_user_id:
        return "not_card_owner", None

    if len(lobby.member_links) >= lobby.max_players:
        return "lobby_full", None

    next_seat = max((m.seat_order for m in lobby.member_links), default=-1) + 1
    session.add(
        LobbyMembership(
            lobby_id=lobby_id,
            player_card_id=player_card_id,
            seat_order=next_seat,
        ),
    )
    await session.commit()
    return None, await get_lobby_with_players(session, lobby_id)


async def set_membership_game_role(
    session: AsyncSession,
    lobby_id: uuid.UUID,
    player_card_id: uuid.UUID,
    game_role: GameRole,
    acting_user_id: uuid.UUID,
) -> tuple[str | None, GameLobbyPublic | None]:
    """Устарело при дублях карточки: используйте set_membership_game_role_for_seat."""
    err, _ = await _require_lobby_host(session, lobby_id, acting_user_id)
    if err:
        return err, None
    membership_stmt = (
        select(LobbyMembership)
        .where(
            LobbyMembership.lobby_id == lobby_id,
            LobbyMembership.player_card_id == player_card_id,
        )
        .order_by(LobbyMembership.joined_at.desc())
    )
    membership = (await session.execute(membership_stmt)).scalars().first()
    if membership is None:
        return "membership_not_found", None
    membership.game_role = game_role
    await session.commit()
    return None, await get_lobby_with_players(session, lobby_id)


async def clear_membership_game_role(
    session: AsyncSession,
    lobby_id: uuid.UUID,
    player_card_id: uuid.UUID,
    acting_user_id: uuid.UUID,
) -> tuple[str | None, GameLobbyPublic | None]:
    """Устарело при дублях карточки: используйте clear_membership_game_role_for_seat."""
    err, _ = await _require_lobby_host(session, lobby_id, acting_user_id)
    if err:
        return err, None
    membership_stmt = (
        select(LobbyMembership)
        .where(
            LobbyMembership.lobby_id == lobby_id,
            LobbyMembership.player_card_id == player_card_id,
        )
        .order_by(LobbyMembership.joined_at.desc())
    )
    membership = (await session.execute(membership_stmt)).scalars().first()
    if membership is None:
        return "membership_not_found", None
    membership.game_role = None
    await session.commit()
    return None, await get_lobby_with_players(session, lobby_id)


async def set_membership_game_role_for_seat(
    session: AsyncSession,
    lobby_id: uuid.UUID,
    membership_id: uuid.UUID,
    game_role: GameRole,
    acting_user_id: uuid.UUID,
) -> tuple[str | None, GameLobbyPublic | None]:
    err, _ = await _require_lobby_host(session, lobby_id, acting_user_id)
    if err:
        return err, None
    m = await session.get(LobbyMembership, membership_id)
    if m is None or m.lobby_id != lobby_id:
        return "membership_not_found", None
    m.game_role = game_role
    await session.commit()
    return None, await get_lobby_with_players(session, lobby_id)


async def clear_membership_game_role_for_seat(
    session: AsyncSession,
    lobby_id: uuid.UUID,
    membership_id: uuid.UUID,
    acting_user_id: uuid.UUID,
) -> tuple[str | None, GameLobbyPublic | None]:
    err, _ = await _require_lobby_host(session, lobby_id, acting_user_id)
    if err:
        return err, None
    m = await session.get(LobbyMembership, membership_id)
    if m is None or m.lobby_id != lobby_id:
        return "membership_not_found", None
    m.game_role = None
    await session.commit()
    return None, await get_lobby_with_players(session, lobby_id)


async def clear_all_lobby_game_roles(
    session: AsyncSession,
    lobby_id: uuid.UUID,
    acting_user_id: uuid.UUID,
) -> tuple[str | None, GameLobbyPublic | None]:
    lobby = await session.get(GameLobby, lobby_id)
    if lobby is None:
        return "lobby_not_found", None
    if lobby.host_user_id is None or lobby.host_user_id != acting_user_id:
        return "not_host", None

    await session.execute(
        update(LobbyMembership)
        .where(LobbyMembership.lobby_id == lobby_id)
        .values(game_role=None)
    )
    await session.commit()
    return None, await get_lobby_with_players(session, lobby_id)


async def set_membership_status(
    session: AsyncSession,
    lobby_id: uuid.UUID,
    player_card_id: uuid.UUID,
    status: GameStatus,
    acting_user_id: uuid.UUID,
) -> tuple[str | None, GameLobbyPublic | None]:
    """Устарело при дублях карточки: используйте set_membership_status_for_seat."""
    err, _ = await _require_lobby_host(session, lobby_id, acting_user_id)
    if err:
        return err, None
    membership_stmt = (
        select(LobbyMembership)
        .where(
            LobbyMembership.lobby_id == lobby_id,
            LobbyMembership.player_card_id == player_card_id,
        )
        .order_by(LobbyMembership.joined_at.desc())
    )
    membership = (await session.execute(membership_stmt)).scalars().first()
    if membership is None:
        return "membership_not_found", None
    membership.status = status
    await session.commit()
    return None, await get_lobby_with_players(session, lobby_id)


async def clear_membership_status(
    session: AsyncSession,
    lobby_id: uuid.UUID,
    player_card_id: uuid.UUID,
    acting_user_id: uuid.UUID,
) -> tuple[str | None, GameLobbyPublic | None]:
    """Устарело при дублях карточки: используйте clear_membership_status_for_seat."""
    err, _ = await _require_lobby_host(session, lobby_id, acting_user_id)
    if err:
        return err, None
    membership_stmt = (
        select(LobbyMembership)
        .where(
            LobbyMembership.lobby_id == lobby_id,
            LobbyMembership.player_card_id == player_card_id,
        )
        .order_by(LobbyMembership.joined_at.desc())
    )
    membership = (await session.execute(membership_stmt)).scalars().first()
    if membership is None:
        return "membership_not_found", None
    membership.status = None
    await session.commit()
    return None, await get_lobby_with_players(session, lobby_id)


async def set_membership_status_for_seat(
    session: AsyncSession,
    lobby_id: uuid.UUID,
    membership_id: uuid.UUID,
    status: GameStatus,
    acting_user_id: uuid.UUID,
) -> tuple[str | None, GameLobbyPublic | None]:
    err, _ = await _require_lobby_host(session, lobby_id, acting_user_id)
    if err:
        return err, None
    m = await session.get(LobbyMembership, membership_id)
    if m is None or m.lobby_id != lobby_id:
        return "membership_not_found", None
    m.status = status
    await session.commit()
    return None, await get_lobby_with_players(session, lobby_id)


async def clear_membership_status_for_seat(
    session: AsyncSession,
    lobby_id: uuid.UUID,
    membership_id: uuid.UUID,
    acting_user_id: uuid.UUID,
) -> tuple[str | None, GameLobbyPublic | None]:
    err, _ = await _require_lobby_host(session, lobby_id, acting_user_id)
    if err:
        return err, None
    m = await session.get(LobbyMembership, membership_id)
    if m is None or m.lobby_id != lobby_id:
        return "membership_not_found", None
    m.status = None
    await session.commit()
    return None, await get_lobby_with_players(session, lobby_id)


async def clear_all_lobby_statuses(
    session: AsyncSession,
    lobby_id: uuid.UUID,
    acting_user_id: uuid.UUID,
) -> tuple[str | None, GameLobbyPublic | None]:
    lobby = await session.get(GameLobby, lobby_id)
    if lobby is None:
        return "lobby_not_found", None
    if lobby.host_user_id is None or lobby.host_user_id != acting_user_id:
        return "not_host", None

    await session.execute(
        update(LobbyMembership)
        .where(LobbyMembership.lobby_id == lobby_id)
        .values(status=None)
    )
    await session.commit()
    return None, await get_lobby_with_players(session, lobby_id)


async def swap_lobby_seats(
    session: AsyncSession,
    lobby_id: uuid.UUID,
    membership_id_a: uuid.UUID,
    membership_id_b: uuid.UUID,
    acting_user_id: uuid.UUID,
) -> tuple[str | None, GameLobbyPublic | None]:
    if membership_id_a == membership_id_b:
        return "same_seat", None

    lobby = await session.get(GameLobby, lobby_id)
    if lobby is None:
        return "lobby_not_found", None
    if lobby.host_user_id is None or lobby.host_user_id != acting_user_id:
        return "not_host", None

    ma = await session.get(LobbyMembership, membership_id_a)
    mb = await session.get(LobbyMembership, membership_id_b)
    if ma is None or mb is None:
        return "membership_not_found", None
    if ma.lobby_id != lobby_id or mb.lobby_id != lobby_id:
        return "membership_not_found", None

    sa, sb = ma.seat_order, mb.seat_order
    ma.seat_order = sb
    mb.seat_order = sa
    await session.commit()
    return None, await get_lobby_with_players(session, lobby_id)


async def replace_lobby_member_card(
    session: AsyncSession,
    lobby_id: uuid.UUID,
    membership_id: uuid.UUID,
    new_player_card_id: uuid.UUID,
    acting_user_id: uuid.UUID,
) -> tuple[str | None, GameLobbyPublic | None]:
    lobby = await session.get(GameLobby, lobby_id)
    if lobby is None:
        return "lobby_not_found", None
    if lobby.host_user_id is None or lobby.host_user_id != acting_user_id:
        return "not_host", None

    m = await session.get(LobbyMembership, membership_id)
    if m is None or m.lobby_id != lobby_id:
        return "membership_not_found", None

    card = await session.get(PlayerCard, new_player_card_id)
    if card is None:
        return "card_not_found", None

    m.player_card_id = new_player_card_id
    m.lobby_photo_url = None
    await session.commit()
    return None, await get_lobby_with_players(session, lobby_id)


def _normalized_card_photo_urls(card: PlayerCard) -> set[str]:
    out: set[str] = set()
    for u in card.photo_urls or []:
        if isinstance(u, str) and u.strip():
            out.add(u.strip())
    return out


async def set_lobby_member_display_photo(
    session: AsyncSession,
    lobby_id: uuid.UUID,
    membership_id: uuid.UUID,
    photo_url: str,
    acting_user_id: uuid.UUID,
) -> tuple[str | None, GameLobbyPublic | None]:
    lobby = await session.get(GameLobby, lobby_id)
    if lobby is None:
        return "lobby_not_found", None
    if lobby.host_user_id is None or lobby.host_user_id != acting_user_id:
        return "not_host", None

    m = await session.get(LobbyMembership, membership_id)
    if m is None or m.lobby_id != lobby_id:
        return "membership_not_found", None

    card = await session.get(PlayerCard, m.player_card_id)
    if card is None:
        return "card_not_found", None

    want = photo_url.strip()
    if want not in _normalized_card_photo_urls(card):
        return "invalid_photo_url", None

    m.lobby_photo_url = want
    await session.commit()
    return None, await get_lobby_with_players(session, lobby_id)


async def clear_lobby_member_display_photo(
    session: AsyncSession,
    lobby_id: uuid.UUID,
    membership_id: uuid.UUID,
    acting_user_id: uuid.UUID,
) -> tuple[str | None, GameLobbyPublic | None]:
    lobby = await session.get(GameLobby, lobby_id)
    if lobby is None:
        return "lobby_not_found", None
    if lobby.host_user_id is None or lobby.host_user_id != acting_user_id:
        return "not_host", None

    m = await session.get(LobbyMembership, membership_id)
    if m is None or m.lobby_id != lobby_id:
        return "membership_not_found", None

    m.lobby_photo_url = None
    await session.commit()
    return None, await get_lobby_with_players(session, lobby_id)
