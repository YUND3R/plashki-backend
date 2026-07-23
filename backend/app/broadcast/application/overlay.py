import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.commerce.application.contracts import OverlayDesignAccessPort
from app.core.overlay_design_catalog import get_catalog_entry
from app.db.base import OverlayDesign
from app.db.models import GameLobby, LobbyMembership, LobbyOverlayState, UserProfile
from app.schemas.lobby import (
    ActiveOverlayLobbyResponse,
    GameLobbyPublic,
    LobbyOverlayDesignOption,
    LobbyOverlayDesignsResponse,
    LobbyOverlayStateResponse,
    OverlayDesignCatalogResponse,
    OverlayLiveStateResponse,
    OverlayPlayerState,
)
from app.sessions.application.lobbies import get_lobby_with_players, require_lobby_host


def _option_response(option) -> LobbyOverlayDesignOption:
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


async def _catalog(access: OverlayDesignAccessPort, user_id: uuid.UUID | None):
    return [_option_response(item) for item in await access.options_for_user(user_id)]


async def get_overlay_design_catalog_for_user(
    session: AsyncSession,
    user_id: uuid.UUID,
    design_access: OverlayDesignAccessPort,
) -> OverlayDesignCatalogResponse | None:
    if await session.get(UserProfile, user_id) is None:
        return None
    return OverlayDesignCatalogResponse(options=await _catalog(design_access, user_id))


async def get_overlay_design_options(
    session: AsyncSession,
    lobby_id: uuid.UUID,
    design_access: OverlayDesignAccessPort,
    viewer_user_id: uuid.UUID | None = None,
) -> LobbyOverlayDesignsResponse | None:
    lobby = await session.get(GameLobby, lobby_id)
    if lobby is None or (
        viewer_user_id is not None and lobby.host_user_id != viewer_user_id
    ):
        return None
    return LobbyOverlayDesignsResponse(
        lobby_id=lobby.id,
        selected_overlay_design=lobby.selected_overlay_design,
        options=await _catalog(design_access, lobby.host_user_id),
    )


async def _overlay_state(
    lobby: GameLobby, design_access: OverlayDesignAccessPort
) -> LobbyOverlayStateResponse:
    members = sorted(lobby.member_links, key=lambda member: (member.seat_order, member.joined_at))
    return LobbyOverlayStateResponse(
        lobby_id=lobby.id,
        selected_overlay_design=lobby.selected_overlay_design,
        active_overlay_screen=lobby.active_overlay_screen,
        design_catalog=await _catalog(design_access, lobby.host_user_id),
        design_access_active=await design_access.host_has_access(
            lobby.host_user_id, lobby.selected_overlay_design
        ),
        sheriff_check=list(lobby.sheriff_check or []),
        best_move=list(lobby.best_move or []),
        players=[
            OverlayPlayerState(
                seat_order=member.seat_order,
                membership_id=member.id,
                nickname=member.player_card.nickname,
                lobby_photo_url=member.lobby_photo_url,
                game_role=member.game_role.value if member.game_role else None,
                status=member.status.value if member.status else None,
                best_move=list(member.best_move or []),
                bonus_points=member.bonus_points,
            )
            for member in members
        ],
    )


def _overlay_query():
    return select(GameLobby).options(
        selectinload(GameLobby.member_links).selectinload(LobbyMembership.player_card)
    )


async def get_lobby_overlay_state(
    session: AsyncSession,
    lobby_id: uuid.UUID,
    design_access: OverlayDesignAccessPort,
    viewer_user_id: uuid.UUID | None = None,
) -> LobbyOverlayStateResponse | None:
    lobby = (
        await session.execute(_overlay_query().where(GameLobby.id == lobby_id))
    ).scalar_one_or_none()
    if lobby is None or (
        viewer_user_id is not None and lobby.host_user_id != viewer_user_id
    ):
        return None
    return await _overlay_state(lobby, design_access)


async def get_lobby_overlay_state_by_public_id(
    session: AsyncSession,
    overlay_public_id: uuid.UUID,
    design_access: OverlayDesignAccessPort,
    expected_lobby_id: uuid.UUID | None = None,
) -> LobbyOverlayStateResponse | None:
    stmt = (
        _overlay_query()
        .join(GameLobby.overlay_state)
        .where(LobbyOverlayState.overlay_public_id == overlay_public_id)
    )
    if expected_lobby_id is not None:
        stmt = stmt.where(GameLobby.id == expected_lobby_id)
    lobby = (await session.execute(stmt)).scalar_one_or_none()
    return None if lobby is None else await _overlay_state(lobby, design_access)


async def set_active_overlay_lobby(
    session: AsyncSession, acting_user_id: uuid.UUID, lobby_id: uuid.UUID
) -> tuple[str | None, ActiveOverlayLobbyResponse | None]:
    err, _ = await require_lobby_host(session, lobby_id, acting_user_id)
    if err:
        return err, None
    user = await session.get(UserProfile, acting_user_id)
    if user is None:
        return "user_not_found", None
    settings = getattr(user, "broadcast_settings", user)
    settings.active_overlay_lobby_id = lobby_id
    await session.commit()
    await session.refresh(settings)
    return None, ActiveOverlayLobbyResponse(
        active_lobby_id=settings.active_overlay_lobby_id,
        updated_at=getattr(settings, "updated_at", user.updated_at),
    )


async def get_active_overlay_state_for_user(
    session: AsyncSession, acting_user_id: uuid.UUID
) -> tuple[str | None, OverlayLiveStateResponse | None]:
    user = await session.get(UserProfile, acting_user_id)
    if user is None:
        return "user_not_found", None
    settings = getattr(user, "broadcast_settings", user)
    active_lobby_id = settings.active_overlay_lobby_id
    lobby = await session.get(GameLobby, active_lobby_id) if active_lobby_id else None
    if lobby is None:
        if active_lobby_id is not None:
            settings.active_overlay_lobby_id = None
            await session.commit()
        return None, OverlayLiveStateResponse(
            active_lobby_id=None,
            active_overlay_screen="lobby",
            selected_overlay_design=OverlayDesign.CLASSIC,
        )
    return None, OverlayLiveStateResponse(
        active_lobby_id=lobby.id,
        active_overlay_screen=lobby.active_overlay_screen,
        show_victory_scores=getattr(lobby, "show_victory_scores", False),
        selected_overlay_design=lobby.selected_overlay_design,
    )


async def set_lobby_overlay_design(
    session: AsyncSession,
    lobby_id: uuid.UUID,
    overlay_design: OverlayDesign,
    acting_user_id: uuid.UUID,
    design_access: OverlayDesignAccessPort,
) -> tuple[str | None, GameLobbyPublic | None]:
    err, lobby = await require_lobby_host(session, lobby_id, acting_user_id)
    if err or lobby is None:
        return err, None
    if await session.get(UserProfile, acting_user_id) is None:
        return "host_not_found", None
    if get_catalog_entry(overlay_design) is None:
        return "unknown_design", None
    if not await design_access.can_use(acting_user_id, overlay_design):
        return "design_access_required", None
    lobby.selected_overlay_design = overlay_design
    await session.commit()
    return None, await get_lobby_with_players(session, lobby_id)


async def _set_lobby_field(
    session: AsyncSession,
    lobby_id: uuid.UUID,
    acting_user_id: uuid.UUID,
    field: str,
    value,
) -> tuple[str | None, GameLobbyPublic | None]:
    err, lobby = await require_lobby_host(session, lobby_id, acting_user_id)
    if err or lobby is None:
        return err, None
    setattr(lobby, field, value)
    await session.commit()
    return None, await get_lobby_with_players(session, lobby_id)


async def set_lobby_active_overlay_screen(
    session, lobby_id, screen_key, acting_user_id
):
    return await _set_lobby_field(
        session, lobby_id, acting_user_id, "active_overlay_screen", screen_key.strip()
    )


async def set_lobby_victory_scores_visibility(
    session, lobby_id, show_scores, acting_user_id
):
    return await _set_lobby_field(
        session, lobby_id, acting_user_id, "show_victory_scores", show_scores
    )


async def set_lobby_sheriff_check(
    session, lobby_id, sheriff_check, acting_user_id
):
    return await _set_lobby_field(
        session, lobby_id, acting_user_id, "sheriff_check", list(sheriff_check)
    )


async def clear_lobby_sheriff_check(session, lobby_id, acting_user_id):
    return await _set_lobby_field(
        session, lobby_id, acting_user_id, "sheriff_check", []
    )


async def set_lobby_best_move(
    session, lobby_id, membership_id, best_move, acting_user_id
):
    err, _ = await require_lobby_host(session, lobby_id, acting_user_id)
    if err:
        return err, None
    membership = await session.get(LobbyMembership, membership_id)
    if membership is None or membership.lobby_id != lobby_id:
        return "membership_not_found", None
    membership.best_move = list(best_move)
    await session.commit()
    return None, await get_lobby_with_players(session, lobby_id)


async def clear_lobby_best_move(session, lobby_id, acting_user_id):
    err, _ = await require_lobby_host(session, lobby_id, acting_user_id)
    if err:
        return err, None
    await session.execute(
        update(LobbyMembership)
        .where(LobbyMembership.lobby_id == lobby_id)
        .values(best_move=[])
    )
    lobby = await session.get(GameLobby, lobby_id)
    lobby.best_move = []
    await session.commit()
    return None, await get_lobby_with_players(session, lobby_id)


async def set_lobby_bonus_points(
    session, lobby_id, bonus_points, acting_user_id
):
    err, _ = await require_lobby_host(session, lobby_id, acting_user_id)
    if err:
        return err, None
    ids = [membership_id for membership_id, _ in bonus_points]
    if len(ids) != len(set(ids)):
        return "duplicate_membership", None
    memberships = (
        await session.execute(
            select(LobbyMembership).where(LobbyMembership.lobby_id == lobby_id)
        )
    ).scalars().all()
    by_id = {membership.id: membership for membership in memberships}
    if any(membership_id not in by_id for membership_id in ids):
        return "membership_not_found", None
    for membership_id, points in bonus_points:
        by_id[membership_id].bonus_points = points
    await session.commit()
    return None, await get_lobby_with_players(session, lobby_id)
