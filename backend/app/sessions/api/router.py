import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.deps.auth import get_current_user_id
from app.schemas.list_filters import LobbyListFilters
from app.schemas.lobby import (
    CreateGameLobbyBody,
    GameLobbyPublic,
    ImportGomafiaTournamentBody,
    ImportGomafiaTournamentResponse,
    ImportedTournamentParticipantsResponse,
    LobbiesTotalResponse,
    ReplaceLobbyMemberBody,
    SelectImportedLobbyTableBody,
    SetGameRoleBody,
    SetLobbyMemberDisplayPhotoBody,
    SetLobbyStatusBody,
    SwapLobbySeatsBody,
)
from app.sessions.application.gomafia import import_gomafia_tournament_to_lobbies
from app.sessions.application.lobbies import (
    count_game_lobbies,
    create_lobby,
    delete_lobby,
    get_lobby_with_players,
    list_imported_tournament_participants,
    list_lobbies_for_host,
    select_imported_lobby_variant,
)
from app.sessions.application.memberships import (
    add_card_to_lobby,
    clear_all_lobby_game_roles,
    clear_all_lobby_statuses,
    clear_lobby_member_display_photo,
    clear_membership_game_role,
    clear_membership_game_role_for_seat,
    clear_membership_status,
    clear_membership_status_for_seat,
    replace_lobby_member_card,
    set_lobby_member_display_photo,
    set_membership_game_role,
    set_membership_game_role_for_seat,
    set_membership_status,
    set_membership_status_for_seat,
    swap_lobby_seats,
)
from app.shared.api.errors import raise_lobby_host_mutation_error
from app.shared.api.http import set_no_cache_headers

router = APIRouter()


@router.post(
    "/lobbies",
    tags=["lobbies"],
    response_model=GameLobbyPublic,
    summary="Создать пустое игровое лобби",
    description="Создатель — пользователь из JWT (Bearer).",
)
async def post_create_lobby(
    body: CreateGameLobbyBody,
    session: AsyncSession = Depends(get_session),
    user_id: uuid.UUID = Depends(get_current_user_id),
) -> GameLobbyPublic:
    err, lobby = await create_lobby(session, body.max_players, user_id, body.title)
    if err == "host_not_found":
        raise HTTPException(
            status_code=404,
            detail="Пользователь не найден в базе.",
        )
    assert lobby is not None
    return lobby


@router.post(
    "/lobbies/import/gomafia",
    tags=["lobbies"],
    response_model=ImportGomafiaTournamentResponse,
    summary="Импортировать турнир Gomafia в лобби",
    description=(
        "Принимает ссылку на турнир gomafia.pro (tab=games), "
        "создает одно лобби турнира и сохраняет внутри варианты тур/стол."
    ),
)
async def post_import_gomafia_tournament(
    body: ImportGomafiaTournamentBody,
    session: AsyncSession = Depends(get_session),
    current_user_id: uuid.UUID = Depends(get_current_user_id),
) -> ImportGomafiaTournamentResponse:
    err, result = await import_gomafia_tournament_to_lobbies(
        session,
        acting_user_id=current_user_id,
        url=body.url,
    )
    if err == "invalid_url":
        raise HTTPException(
            status_code=422,
            detail="Нужна валидная ссылка на турнир gomafia.pro (/tournament/{id}).",
        )
    if err == "host_not_found":
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    if err == "fetch_failed":
        raise HTTPException(
            status_code=502, detail="Не удалось загрузить страницу турнира."
        )
    if err == "parse_failed":
        raise HTTPException(
            status_code=422,
            detail="Не удалось распарсить туры/игроков из страницы турнира.",
        )
    assert result is not None
    return result


@router.patch(
    "/lobbies/{lobby_id}/imported-selection",
    tags=["lobbies"],
    response_model=GameLobbyPublic,
    summary="Переключить активный тур/стол в импортированном лобби (только хост)",
)
async def patch_imported_lobby_selection(
    lobby_id: uuid.UUID,
    body: SelectImportedLobbyTableBody,
    session: AsyncSession = Depends(get_session),
    acting_user_id: uuid.UUID = Depends(get_current_user_id),
) -> GameLobbyPublic:
    err, lobby = await select_imported_lobby_variant(
        session=session,
        lobby_id=lobby_id,
        variant_key=body.key,
        acting_user_id=acting_user_id,
    )
    if err == "lobby_not_found":
        raise HTTPException(status_code=404, detail="Лобби не найдено")
    if err == "not_host":
        raise HTTPException(
            status_code=403,
            detail="Переключать тур/стол может только хост лобби.",
        )
    if err == "not_imported_lobby":
        raise HTTPException(status_code=422, detail="Это лобби не из импорта Gomafia.")
    if err == "variant_not_found":
        raise HTTPException(status_code=404, detail="Выбранный тур/стол не найден.")
    if err == "variant_invalid":
        raise HTTPException(
            status_code=422, detail="Данные выбранного тура/стола повреждены."
        )
    assert lobby is not None
    return lobby


@router.get(
    "/lobbies/{lobby_id}/imported-participants",
    tags=["lobbies"],
    response_model=ImportedTournamentParticipantsResponse,
    summary="Список всех участников турнира из импорта Gomafia (только хост)",
)
async def get_imported_tournament_participants(
    lobby_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current_user_id: uuid.UUID = Depends(get_current_user_id),
) -> ImportedTournamentParticipantsResponse:
    err, result = await list_imported_tournament_participants(
        session=session,
        lobby_id=lobby_id,
        viewer_user_id=current_user_id,
    )
    if err == "lobby_not_found":
        raise HTTPException(status_code=404, detail="Лобби не найдено")
    if err == "not_host":
        raise HTTPException(status_code=403, detail="Доступно только хосту лобби.")
    if err == "not_imported_lobby":
        raise HTTPException(status_code=422, detail="Это лобби не из импорта Gomafia.")
    assert result is not None
    return result


@router.get(
    "/lobbies",
    tags=["lobbies"],
    response_model=list[GameLobbyPublic],
    summary="Лобби текущего пользователя",
    description="Фильтр source: all (все), created (созданные вручную), imported (из Gomafia).",
)
async def get_my_lobbies(
    session: AsyncSession = Depends(get_session),
    current_user_id: uuid.UUID = Depends(get_current_user_id),
    filters: LobbyListFilters = Depends(),
) -> list[GameLobbyPublic]:
    return await list_lobbies_for_host(session, current_user_id, filters=filters)


@router.get(
    "/lobbies/count",
    tags=["lobbies"],
    response_model=LobbiesTotalResponse,
    summary="Сколько лобби у текущего пользователя",
    description="Тот же фильтр source, что и у GET /lobbies.",
)
async def get_lobbies_count(
    session: AsyncSession = Depends(get_session),
    current_user_id: uuid.UUID = Depends(get_current_user_id),
    filters: LobbyListFilters = Depends(),
) -> LobbiesTotalResponse:
    total = await count_game_lobbies(
        session, host_user_id=current_user_id, filters=filters
    )
    return LobbiesTotalResponse(total=total)


@router.get(
    "/lobbies/{lobby_id}",
    tags=["lobbies"],
    response_model=GameLobbyPublic,
    summary="Лобби: места привязаны к карточкам (ник и фото с карточки, логин — владельца)",
)
async def get_lobby(
    lobby_id: uuid.UUID,
    response: Response,
    session: AsyncSession = Depends(get_session),
    current_user_id: uuid.UUID = Depends(get_current_user_id),
) -> GameLobbyPublic:
    set_no_cache_headers(response)
    lobby = await get_lobby_with_players(
        session, lobby_id, viewer_user_id=current_user_id
    )
    if lobby is None:
        raise HTTPException(status_code=404, detail="Лобби не найдено")
    return lobby


@router.delete(
    "/lobbies/{lobby_id}",
    tags=["lobbies"],
    summary="Удалить лобби (только хост)",
)
async def delete_lobby_endpoint(
    lobby_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    acting_user_id: uuid.UUID = Depends(get_current_user_id),
) -> dict[str, bool]:
    err = await delete_lobby(session, lobby_id, acting_user_id)
    if err == "lobby_not_found":
        raise HTTPException(status_code=404, detail="Лобби не найдено")
    if err == "not_host":
        raise HTTPException(
            status_code=403,
            detail="Удалять лобби может только хост.",
        )
    return {"ok": True}


@router.post(
    "/lobbies/{lobby_id}/player-cards/{player_card_id}",
    tags=["lobbies"],
    response_model=GameLobbyPublic,
    summary="Добавить в лобби свою карточку игрока",
    description="В лобби — только player_card. Владелец карточки должен совпадать с пользователем из JWT.",
)
async def post_add_lobby_player_card(
    lobby_id: uuid.UUID,
    player_card_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    acting_user_id: uuid.UUID = Depends(get_current_user_id),
) -> GameLobbyPublic:
    err, lobby = await add_card_to_lobby(
        session, lobby_id, player_card_id, acting_user_id
    )
    if err == "lobby_not_found":
        raise HTTPException(status_code=404, detail="Лобби не найдено")
    if err == "card_not_found":
        raise HTTPException(status_code=404, detail="Карточка не найдена")
    if err == "not_card_owner":
        raise HTTPException(
            status_code=403,
            detail="Можно добавлять только свои карточки (owner_user_id ≠ acting_user_id).",
        )
    if err == "lobby_full":
        raise HTTPException(status_code=409, detail="Лобби заполнено")
    assert lobby is not None
    return lobby


@router.post(
    "/lobbies/{lobby_id}/members/swap",
    tags=["lobbies"],
    response_model=GameLobbyPublic,
    summary="Поменять двух игроков местами (только хост лобби, Bearer JWT)",
    description=(
        "Тело JSON: **membership_id_a**, **membership_id_b** — id строк `lobby_membership` "
        "(поле **membership_id** в элементах списка **players** у GET /lobbies/{id})."
    ),
)
async def post_swap_lobby_members(
    lobby_id: uuid.UUID,
    body: SwapLobbySeatsBody,
    session: AsyncSession = Depends(get_session),
    acting_user_id: uuid.UUID = Depends(get_current_user_id),
) -> GameLobbyPublic:
    err, lobby = await swap_lobby_seats(
        session,
        lobby_id,
        body.membership_id_a,
        body.membership_id_b,
        acting_user_id,
    )
    if err == "same_seat":
        raise HTTPException(status_code=400, detail="Укажите два разных места.")
    if err == "lobby_not_found":
        raise HTTPException(status_code=404, detail="Лобби не найдено")
    if err == "not_host":
        raise HTTPException(
            status_code=403,
            detail="Менять порядок может только хост лобби.",
        )
    if err == "membership_not_found":
        raise HTTPException(
            status_code=404,
            detail="Игрок не найден в этом лобби.",
        )
    assert lobby is not None
    return lobby


@router.patch(
    "/lobbies/{lobby_id}/members/{membership_id}/display-photo",
    tags=["lobbies"],
    response_model=GameLobbyPublic,
    summary="Фото участника в лобби (URL из photo_urls карточки), только хост",
    description="JSON: **photo_url** — один из URL из **photo_urls** текущей карточки на этом месте.",
)
async def patch_lobby_member_display_photo(
    lobby_id: uuid.UUID,
    membership_id: uuid.UUID,
    body: SetLobbyMemberDisplayPhotoBody,
    session: AsyncSession = Depends(get_session),
    acting_user_id: uuid.UUID = Depends(get_current_user_id),
) -> GameLobbyPublic:
    err, lobby = await set_lobby_member_display_photo(
        session,
        lobby_id,
        membership_id,
        body.photo_url,
        acting_user_id,
    )
    if err == "lobby_not_found":
        raise HTTPException(status_code=404, detail="Лобби не найдено")
    if err == "not_host":
        raise HTTPException(
            status_code=403,
            detail="Менять отображение может только хост лобби.",
        )
    if err == "membership_not_found":
        raise HTTPException(status_code=404, detail="Место в лобби не найдено.")
    if err == "card_not_found":
        raise HTTPException(status_code=404, detail="Карточка не найдена.")
    if err == "invalid_photo_url":
        raise HTTPException(
            status_code=422,
            detail="Укажите URL из списка фото карточки игрока на этом месте.",
        )
    assert lobby is not None
    return lobby


@router.delete(
    "/lobbies/{lobby_id}/members/{membership_id}/display-photo",
    tags=["lobbies"],
    response_model=GameLobbyPublic,
    summary="Сбросить фото участника в лобби (только хост)",
)
async def delete_lobby_member_display_photo(
    lobby_id: uuid.UUID,
    membership_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    acting_user_id: uuid.UUID = Depends(get_current_user_id),
) -> GameLobbyPublic:
    err, lobby = await clear_lobby_member_display_photo(
        session,
        lobby_id,
        membership_id,
        acting_user_id,
    )
    if err == "lobby_not_found":
        raise HTTPException(status_code=404, detail="Лобби не найдено")
    if err == "not_host":
        raise HTTPException(
            status_code=403,
            detail="Менять отображение может только хост лобби.",
        )
    if err == "membership_not_found":
        raise HTTPException(status_code=404, detail="Место в лобби не найдено.")
    assert lobby is not None
    return lobby


@router.patch(
    "/lobbies/{lobby_id}/members/{membership_id}",
    tags=["lobbies"],
    response_model=GameLobbyPublic,
    summary="Поменять игрока на месте (другая карточка), только хост лобби",
    description="JSON: **player_card_id** — новая карточка игрока. **membership_id** — из списка **players** в GET лобби.",
)
async def patch_lobby_member(
    lobby_id: uuid.UUID,
    membership_id: uuid.UUID,
    body: ReplaceLobbyMemberBody,
    session: AsyncSession = Depends(get_session),
    acting_user_id: uuid.UUID = Depends(get_current_user_id),
) -> GameLobbyPublic:
    err, lobby = await replace_lobby_member_card(
        session,
        lobby_id,
        membership_id,
        body.player_card_id,
        acting_user_id,
    )
    if err == "lobby_not_found":
        raise HTTPException(status_code=404, detail="Лобби не найдено")
    if err == "not_host":
        raise HTTPException(
            status_code=403,
            detail="Менять состав может только хост лобби.",
        )
    if err == "membership_not_found":
        raise HTTPException(status_code=404, detail="Место в лобби не найдено.")
    if err == "card_not_found":
        raise HTTPException(status_code=404, detail="Карточка не найдена.")
    assert lobby is not None
    return lobby


@router.patch(
    "/lobbies/{lobby_id}/members/{membership_id}/game-role",
    tags=["lobbies"],
    response_model=GameLobbyPublic,
    summary="Назначить игровую роль на место в лобби (по membership_id, только хост)",
    description="У каждого места своя роль — при дублях одной карточки роли могут различаться. **membership_id** из GET лобби.",
)
async def patch_member_game_role(
    lobby_id: uuid.UUID,
    membership_id: uuid.UUID,
    body: SetGameRoleBody,
    session: AsyncSession = Depends(get_session),
    acting_user_id: uuid.UUID = Depends(get_current_user_id),
) -> GameLobbyPublic:
    err, lobby = await set_membership_game_role_for_seat(
        session, lobby_id, membership_id, body.game_role, acting_user_id
    )
    raise_lobby_host_mutation_error(err)
    assert lobby is not None
    return lobby


@router.delete(
    "/lobbies/{lobby_id}/members/{membership_id}/game-role",
    tags=["lobbies"],
    response_model=GameLobbyPublic,
    summary="Сбросить игровую роль на месте в лобби (по membership_id, только хост)",
)
async def delete_member_game_role(
    lobby_id: uuid.UUID,
    membership_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    acting_user_id: uuid.UUID = Depends(get_current_user_id),
) -> GameLobbyPublic:
    err, lobby = await clear_membership_game_role_for_seat(
        session, lobby_id, membership_id, acting_user_id
    )
    raise_lobby_host_mutation_error(err)
    assert lobby is not None
    return lobby


@router.delete(
    "/lobbies/{lobby_id}/game-roles",
    tags=["lobbies"],
    response_model=GameLobbyPublic,
    summary="Сбросить игровые роли у всех мест в лобби (только хост)",
)
async def delete_all_lobby_game_roles(
    lobby_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    acting_user_id: uuid.UUID = Depends(get_current_user_id),
) -> GameLobbyPublic:
    err, lobby = await clear_all_lobby_game_roles(session, lobby_id, acting_user_id)
    if err == "lobby_not_found":
        raise HTTPException(status_code=404, detail="Лобби не найдено")
    if err == "not_host":
        raise HTTPException(
            status_code=403,
            detail="Сбрасывать роли может только хост лобби.",
        )
    assert lobby is not None
    return lobby


@router.patch(
    "/lobbies/{lobby_id}/player-cards/{player_card_id}/game-role",
    tags=["lobbies"],
    response_model=GameLobbyPublic,
    summary="Назначить игровую роль по карточке (только хост)",
    description="Если одна карточка в лобби несколько раз, используйте **PATCH …/members/{membership_id}/game-role**.",
)
async def patch_player_game_role(
    lobby_id: uuid.UUID,
    player_card_id: uuid.UUID,
    body: SetGameRoleBody,
    session: AsyncSession = Depends(get_session),
    acting_user_id: uuid.UUID = Depends(get_current_user_id),
) -> GameLobbyPublic:
    err, lobby = await set_membership_game_role(
        session, lobby_id, player_card_id, body.game_role, acting_user_id
    )
    raise_lobby_host_mutation_error(err)
    assert lobby is not None
    return lobby


@router.delete(
    "/lobbies/{lobby_id}/player-cards/{player_card_id}/game-role",
    tags=["lobbies"],
    response_model=GameLobbyPublic,
    summary="Сбросить роль по карточке (только хост)",
    description="При дублях карточки — **DELETE …/members/{membership_id}/game-role**.",
)
async def delete_player_game_role(
    lobby_id: uuid.UUID,
    player_card_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    acting_user_id: uuid.UUID = Depends(get_current_user_id),
) -> GameLobbyPublic:
    err, lobby = await clear_membership_game_role(
        session, lobby_id, player_card_id, acting_user_id
    )
    raise_lobby_host_mutation_error(err)
    assert lobby is not None
    return lobby


@router.patch(
    "/lobbies/{lobby_id}/members/{membership_id}/status",
    tags=["lobbies"],
    response_model=GameLobbyPublic,
    summary="Назначить статус на место в игровом лобби (по membership_id, только хост)",
    description="У каждого места свой статус. **membership_id** берите из GET лобби.",
)
async def patch_member_status(
    lobby_id: uuid.UUID,
    membership_id: uuid.UUID,
    body: SetLobbyStatusBody,
    session: AsyncSession = Depends(get_session),
    acting_user_id: uuid.UUID = Depends(get_current_user_id),
) -> GameLobbyPublic:
    err, lobby = await set_membership_status_for_seat(
        session, lobby_id, membership_id, body.status, acting_user_id
    )
    raise_lobby_host_mutation_error(err)
    assert lobby is not None
    return lobby


@router.delete(
    "/lobbies/{lobby_id}/members/{membership_id}/status",
    tags=["lobbies"],
    response_model=GameLobbyPublic,
    summary="Сбросить статус на месте в игровом лобби (по membership_id, только хост)",
)
async def delete_member_status(
    lobby_id: uuid.UUID,
    membership_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    acting_user_id: uuid.UUID = Depends(get_current_user_id),
) -> GameLobbyPublic:
    err, lobby = await clear_membership_status_for_seat(
        session, lobby_id, membership_id, acting_user_id
    )
    raise_lobby_host_mutation_error(err)
    assert lobby is not None
    return lobby


@router.delete(
    "/lobbies/{lobby_id}/statuses",
    tags=["lobbies"],
    response_model=GameLobbyPublic,
    summary="Сбросить статусы у всех мест в лобби (только хост)",
)
async def delete_all_lobby_statuses(
    lobby_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    acting_user_id: uuid.UUID = Depends(get_current_user_id),
) -> GameLobbyPublic:
    err, lobby = await clear_all_lobby_statuses(session, lobby_id, acting_user_id)
    if err == "lobby_not_found":
        raise HTTPException(status_code=404, detail="Лобби не найдено")
    if err == "not_host":
        raise HTTPException(
            status_code=403,
            detail="Сбрасывать статусы может только хост лобби.",
        )
    assert lobby is not None
    return lobby


@router.patch(
    "/lobbies/{lobby_id}/player-cards/{player_card_id}/status",
    tags=["lobbies"],
    response_model=GameLobbyPublic,
    summary="Назначить статус по карточке (только хост)",
    description="Если одна карточка в лобби несколько раз, используйте **PATCH …/members/{membership_id}/status**.",
)
async def patch_player_status(
    lobby_id: uuid.UUID,
    player_card_id: uuid.UUID,
    body: SetLobbyStatusBody,
    session: AsyncSession = Depends(get_session),
    acting_user_id: uuid.UUID = Depends(get_current_user_id),
) -> GameLobbyPublic:
    err, lobby = await set_membership_status(
        session, lobby_id, player_card_id, body.status, acting_user_id
    )
    raise_lobby_host_mutation_error(err)
    assert lobby is not None
    return lobby


@router.delete(
    "/lobbies/{lobby_id}/player-cards/{player_card_id}/status",
    tags=["lobbies"],
    response_model=GameLobbyPublic,
    summary="Сбросить статус по карточке (только хост)",
    description="При дублях карточки — **DELETE …/members/{membership_id}/status**.",
)
async def delete_player_status(
    lobby_id: uuid.UUID,
    player_card_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    acting_user_id: uuid.UUID = Depends(get_current_user_id),
) -> GameLobbyPublic:
    err, lobby = await clear_membership_status(
        session, lobby_id, player_card_id, acting_user_id
    )
    raise_lobby_host_mutation_error(err)
    assert lobby is not None
    return lobby
