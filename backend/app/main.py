import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.staticfiles import StaticFiles

from app.core.config import settings
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.core.role import (
    admin_list_registered_users,
    admin_update_user_access,
    delete_moderator_role_from_user,
    delete_sponsor_role_from_user,
    update_user_role_user_to_moderator,
    update_user_role_user_to_sponsor,
)
from app.db import models as _models  # noqa: F401 — регистрация моделей в metadata
from app.db.base import Base, OverlayDesign
from app.db.session import engine, get_session
from app.deps.auth import get_current_user_id
from app.routers import auth as auth_routes
from app.routers import dev as dev_routes
from app.routers import feedback as feedback_routes
from app.routers import nanobanana as nanobanana_routes
from app.routers import player_card as player_card_routes
from app.schemas.list_filters import AdminUserListFilters, LobbyListFilters
from app.schemas.lobby import (
    ActiveOverlayLobbyResponse,
    CreateGameLobbyBody,
    GameLobbyPublic,
    ImportGomafiaTournamentBody,
    ImportGomafiaTournamentResponse,
    ImportedTournamentParticipantsResponse,
    OverlayDesignCatalogResponse,
    LobbyOverlayDesignsResponse,
    LobbyOverlayStateResponse,
    LobbiesTotalResponse,
    OverlayLiveStateResponse,
    ReplaceLobbyMemberBody,
    SetActiveOverlayLobbyBody,
    SetBestMoveBody,
    SetGameRoleBody,
    SetActiveOverlayScreenBody,
    SetOverlayDesignBody,
    SelectImportedLobbyTableBody,
    SetSheriffCheckBody,
    SetLobbyStatusBody,
    SetLobbyMemberDisplayPhotoBody,
    SwapLobbySeatsBody,
)
from app.schemas.auth import (
    AdminRegisteredUser,
    AdminUpdateUserAccessBody,
    AdminUserAccessResponse,
)
from app.services.gomafia_import import import_gomafia_tournament_to_lobbies
from app.services.lobby import (
    add_card_to_lobby,
    clear_lobby_best_move,
    clear_lobby_member_display_photo,
    clear_lobby_sheriff_check,
    clear_all_lobby_game_roles,
    clear_all_lobby_statuses,
    clear_membership_game_role,
    clear_membership_game_role_for_seat,
    clear_membership_status,
    clear_membership_status_for_seat,
    count_game_lobbies,
    create_lobby,
    delete_lobby,
    list_lobbies_for_host,
    get_lobby_with_players,
    get_lobby_overlay_state,
    get_lobby_overlay_state_by_public_id,
    get_active_overlay_state_for_user,
    list_imported_tournament_participants,
    get_overlay_design_catalog_for_user,
    get_overlay_design_options,
    replace_lobby_member_card,
    set_lobby_overlay_design,
    set_lobby_active_overlay_screen,
    set_lobby_member_display_photo,
    set_active_overlay_lobby,
    set_lobby_best_move,
    set_lobby_sheriff_check,
    select_imported_lobby_variant,
    set_membership_game_role,
    set_membership_game_role_for_seat,
    set_membership_status,
    set_membership_status_for_seat,
    swap_lobby_seats,
)

@asynccontextmanager
async def lifespan(_app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Убрали is_primary: индекс и колонка больше не используются
        await conn.execute(
            text("DROP INDEX IF EXISTS uq_player_card_primary_per_owner")
        )
        await conn.execute(text("ALTER TABLE player_card DROP COLUMN IF EXISTS is_primary"))
        # create_all не изменяет существующие таблицы — колонки вручную
        await conn.execute(
            text(
                "ALTER TABLE game_lobby ADD COLUMN IF NOT EXISTS host_user_id UUID "
                "REFERENCES user_profile(id) ON DELETE SET NULL"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE game_lobby ADD COLUMN IF NOT EXISTS selected_overlay_design "
                "VARCHAR(32) NOT NULL DEFAULT 'classic'"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE game_lobby ADD COLUMN IF NOT EXISTS sheriff_check "
                "JSONB NOT NULL DEFAULT '[]'::jsonb"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE game_lobby ADD COLUMN IF NOT EXISTS best_move "
                "JSONB NOT NULL DEFAULT '[]'::jsonb"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE game_lobby ADD COLUMN IF NOT EXISTS title "
                "VARCHAR(120) NOT NULL DEFAULT 'Лобби'"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE game_lobby ADD COLUMN IF NOT EXISTS imported_source_url VARCHAR(1024) NULL"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE game_lobby ADD COLUMN IF NOT EXISTS imported_current_key VARCHAR(120) NULL"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE game_lobby ADD COLUMN IF NOT EXISTS imported_variants "
                "JSONB NOT NULL DEFAULT '[]'::jsonb"
            )
        )
        await conn.execute(
            text(
                "UPDATE game_lobby SET title = 'Лобби' WHERE title IS NULL OR btrim(title) = ''"
            )
        )
        await conn.execute(
            text("ALTER TABLE game_lobby ADD COLUMN IF NOT EXISTS overlay_public_id UUID")
        )
        await conn.execute(
            text(
                "UPDATE game_lobby SET overlay_public_id = md5(random()::text || clock_timestamp()::text)::uuid "
                "WHERE overlay_public_id IS NULL"
            )
        )
        await conn.execute(
            text("ALTER TABLE game_lobby ALTER COLUMN overlay_public_id SET NOT NULL")
        )
        await conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_game_lobby_overlay_public_id "
                "ON game_lobby(overlay_public_id)"
            )
        )
        await conn.execute(
            text(
                "UPDATE game_lobby SET selected_overlay_design = 'classic' "
                "WHERE selected_overlay_design IS NULL OR selected_overlay_design = 'minimal'"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE game_lobby ALTER COLUMN selected_overlay_design SET DEFAULT 'classic'"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE game_lobby ADD COLUMN IF NOT EXISTS active_overlay_screen "
                "VARCHAR(64) NOT NULL DEFAULT 'lobby'"
            )
        )
        await conn.execute(
            text(
                "UPDATE game_lobby SET active_overlay_screen = 'lobby' "
                "WHERE active_overlay_screen IS NULL OR btrim(active_overlay_screen) = ''"
            )
        )
        await conn.execute(
            text(
                """
                DO $lobby_mig$ BEGIN
                  IF EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = 'lobby_membership'
                      AND column_name = 'user_id'
                  ) THEN
                    DROP TABLE lobby_membership CASCADE;
                  END IF;
                END $lobby_mig$;
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE lobby_membership
                ADD COLUMN IF NOT EXISTS id UUID;
                """
            )
        )
        await conn.execute(
            text(
                """
                UPDATE lobby_membership
                SET id = md5(random()::text || clock_timestamp()::text)::uuid
                WHERE id IS NULL;
                """
            )
        )
        await conn.execute(
            text("ALTER TABLE lobby_membership DROP CONSTRAINT IF EXISTS uq_lobby_membership_lobby_card")
        )
        await conn.execute(
            text(
                """
                DO $lobby_pk_mig$ BEGIN
                  IF EXISTS (
                    SELECT 1
                    FROM information_schema.table_constraints
                    WHERE table_schema = 'public'
                      AND table_name = 'lobby_membership'
                      AND constraint_type = 'PRIMARY KEY'
                  ) THEN
                    ALTER TABLE lobby_membership DROP CONSTRAINT lobby_membership_pkey;
                  END IF;
                END $lobby_pk_mig$;
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE lobby_membership
                ADD CONSTRAINT lobby_membership_pkey PRIMARY KEY (id);
                """
            )
        )
        await conn.execute(
            text("ALTER TABLE lobby_membership ADD COLUMN IF NOT EXISTS seat_order SMALLINT")
        )
        await conn.execute(
            text(
                """
                WITH ranked AS (
                  SELECT id,
                    (ROW_NUMBER() OVER (PARTITION BY lobby_id ORDER BY joined_at) - 1)::smallint AS so
                  FROM lobby_membership
                )
                UPDATE lobby_membership m
                SET seat_order = ranked.so
                FROM ranked
                WHERE m.id = ranked.id AND m.seat_order IS NULL;
                """
            )
        )
        await conn.execute(
            text("UPDATE lobby_membership SET seat_order = 0 WHERE seat_order IS NULL")
        )
        await conn.execute(
            text(
                "ALTER TABLE lobby_membership ALTER COLUMN seat_order SET DEFAULT 0"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE lobby_membership ALTER COLUMN seat_order SET NOT NULL"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE lobby_membership ADD COLUMN IF NOT EXISTS lobby_photo_url VARCHAR(1024) NULL"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE lobby_membership ADD COLUMN IF NOT EXISTS status VARCHAR(32) NULL"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE user_profile ADD COLUMN IF NOT EXISTS first_name "
                "VARCHAR(100) NOT NULL DEFAULT ''"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE user_profile ADD COLUMN IF NOT EXISTS last_name "
                "VARCHAR(100) NOT NULL DEFAULT ''"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE user_profile ADD COLUMN IF NOT EXISTS avatar_url VARCHAR(1024) NULL"
            )
        )
        await conn.execute(
            text(
                """
                DO $username_unique$ BEGIN
                  IF NOT EXISTS (
                    SELECT 1
                    FROM pg_class c
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE c.relkind = 'i'
                      AND c.relname = 'uq_user_profile_username'
                      AND n.nspname = 'public'
                  ) THEN
                    IF NOT EXISTS (
                      SELECT 1
                      FROM user_profile
                      GROUP BY username
                      HAVING COUNT(*) > 1
                    ) THEN
                      CREATE UNIQUE INDEX uq_user_profile_username ON user_profile(username);
                    END IF;
                  END IF;
                END $username_unique$;
                """
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE user_profile ADD COLUMN IF NOT EXISTS email_verified_at "
                "TIMESTAMPTZ NULL"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE user_profile ADD COLUMN IF NOT EXISTS active_overlay_lobby_id UUID NULL"
            )
        )
        await conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_user_profile_active_overlay_lobby_id "
                "ON user_profile(active_overlay_lobby_id)"
            )
        )
        await conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS feedback_message (
                    id UUID PRIMARY KEY,
                    user_id UUID NOT NULL REFERENCES user_profile(id) ON DELETE CASCADE,
                    category VARCHAR(32) NOT NULL,
                    message VARCHAR(4000) NOT NULL,
                    page_url VARCHAR(1024) NULL,
                    contact_email VARCHAR(255) NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
        )
        await conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_feedback_message_user_id "
                "ON feedback_message(user_id)"
            )
        )
        await conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS _applied_schema_patch (
                    id TEXT PRIMARY KEY
                )
                """
            )
        )
        patch_row = (
            await conn.execute(
                text(
                    """
                    INSERT INTO _applied_schema_patch (id)
                    VALUES ('user_profile_email_verified_v1')
                    ON CONFLICT (id) DO NOTHING
                    RETURNING id
                    """
                )
            )
        ).first()
        if patch_row is not None:
            await conn.execute(
                text(
                    "UPDATE user_profile SET email_verified_at = created_at "
                    "WHERE email_verified_at IS NULL"
                )
            )
        await conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS pending_registration ("
                "id UUID PRIMARY KEY, "
                "username VARCHAR(55) NOT NULL UNIQUE, "
                "email VARCHAR(55) NOT NULL UNIQUE, "
                "first_name VARCHAR(100) NOT NULL, "
                "last_name VARCHAR(100) NOT NULL, "
                "avatar_url VARCHAR(1024) NULL, "
                "hashed_password VARCHAR(255) NOT NULL, "
                "expires_at TIMESTAMPTZ NOT NULL, "
                "consumed_at TIMESTAMPTZ NULL, "
                "created_at TIMESTAMPTZ NOT NULL DEFAULT now()"
                ")"
            )
        )
        await conn.execute(
            text("ALTER TABLE email_verification_token ALTER COLUMN token_hash DROP NOT NULL")
        )
        await conn.execute(
            text("ALTER TABLE email_verification_token ALTER COLUMN user_id DROP NOT NULL")
        )
        await conn.execute(
            text(
                "ALTER TABLE email_verification_token "
                "ADD COLUMN IF NOT EXISTS pending_registration_id UUID "
                "REFERENCES pending_registration(id) ON DELETE CASCADE"
            )
        )
        await conn.execute(
            text("ALTER TABLE password_reset_token ALTER COLUMN token_hash DROP NOT NULL")
        )
        await conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_pending_registration_username "
                "ON pending_registration(username)"
            )
        )
        await conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_pending_registration_email "
                "ON pending_registration(email)"
            )
        )
        await conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_pending_registration_expires_at "
                "ON pending_registration(expires_at)"
            )
        )
        await conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_email_verification_token_pending_registration_id "
                "ON email_verification_token(pending_registration_id)"
            )
        )
        await conn.run_sync(Base.metadata.create_all)
    up = Path(settings.upload_dir)
    if not up.is_absolute():
        up = Path.cwd() / up
    up.mkdir(parents=True, exist_ok=True)
    yield
    await engine.dispose()

_openapi = "/openapi.json" if settings.expose_openapi else None
_docs = "/docs" if settings.expose_openapi else None
_redoc = "/redoc" if settings.expose_openapi else None

app = FastAPI(
    title="Plashki API",
    version="0.1.0",
    docs_url=_docs,
    redoc_url=_redoc,
    openapi_url=_openapi,
    lifespan=lifespan,
)

if settings.cors_origin_list:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.add_middleware(SecurityHeadersMiddleware)

if settings.dev_endpoints_enabled:
    app.include_router(dev_routes.router)

app.include_router(auth_routes.router)
app.include_router(feedback_routes.router)
app.include_router(player_card_routes.router)
app.include_router(nanobanana_routes.router)


def _set_no_cache_headers(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"


@app.get("/health", tags=["system"])
async def health(session: AsyncSession = Depends(get_session)) -> dict[str, str]:
    await session.execute(text("SELECT 1"))
    return {"status": "ok", "database": "connected"}


@app.patch(
    "/admin/users/{user_id}/sponsor",
    tags=["admin"],
    summary="USER → SPONSOR (только ADMIN)",
)
async def admin_set_sponsor(
    user_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    requester_id: uuid.UUID = Depends(get_current_user_id),
) -> dict[str, bool]:
    ok = await update_user_role_user_to_sponsor(
        session,
        requester_id=requester_id,
        user_id=user_id,
    )
    if not ok:
        raise HTTPException(
            status_code=403,
            detail="Нет прав или пользователь не в роли USER.",
        )
    return {"ok": True}


@app.delete(
    "/admin/users/{user_id}/sponsor",
    tags=["admin"],
    summary="SPONSOR → USER (только ADMIN)",
)
async def admin_delete_sponsor(
    user_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    requester_id: uuid.UUID = Depends(get_current_user_id),
) -> dict[str, bool]:
    ok = await delete_sponsor_role_from_user(
        session,
        requester_id=requester_id,
        user_id=user_id,
    )
    if not ok:
        raise HTTPException(
            status_code=403,
            detail="Нет прав или пользователь не в роли SPONSOR.",
        )
    return {"ok": True}


@app.patch(
    "/admin/users/{user_id}/moderator",
    tags=["admin"],
    summary="USER → MODERATOR (только ADMIN)",
)
async def admin_set_moderator(
    user_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    requester_id: uuid.UUID = Depends(get_current_user_id),
) -> dict[str, bool]:
    ok = await update_user_role_user_to_moderator(
        session,
        requester_id=requester_id,
        user_id=user_id,
    )
    if not ok:
        raise HTTPException(
            status_code=403,
            detail="Нет прав или пользователь не в роли USER.",
        )
    return {"ok": True}


@app.delete(
    "/admin/users/{user_id}/moderator",
    tags=["admin"],
    summary="MODERATOR → USER (только ADMIN)",
)
async def admin_delete_moderator(
    user_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    requester_id: uuid.UUID = Depends(get_current_user_id),
) -> dict[str, bool]:
    ok = await delete_moderator_role_from_user(
        session,
        requester_id=requester_id,
        user_id=user_id,
    )
    if not ok:
        raise HTTPException(
            status_code=403,
            detail="Нет прав или пользователь не в роли MODERATOR.",
        )
    return {"ok": True}


@app.patch(
    "/admin/users/{user_id}/access",
    tags=["admin"],
    response_model=AdminUserAccessResponse,
    summary="Обновить role/subscription пользователя (только ADMIN)",
)
async def admin_patch_user_access(
    user_id: uuid.UUID,
    body: AdminUpdateUserAccessBody,
    session: AsyncSession = Depends(get_session),
    requester_id: uuid.UUID = Depends(get_current_user_id),
) -> AdminUserAccessResponse:
    err, user = await admin_update_user_access(
        session,
        requester_id=requester_id,
        user_id=user_id,
        role=body.role,
        subscription=body.subscription,
    )
    if err == "not_admin":
        raise HTTPException(status_code=403, detail="Только ADMIN может менять доступ.")
    if err == "user_not_found":
        raise HTTPException(status_code=404, detail="Пользователь не найден.")
    if err == "empty_update":
        raise HTTPException(
            status_code=422,
            detail="Укажите хотя бы одно поле: role или subscription.",
        )
    assert user is not None
    return AdminUserAccessResponse(
        id=user.id,
        role=user.role,
        subscription=user.subscription,
    )


@app.get(
    "/admin/users",
    tags=["admin"],
    response_model=list[AdminRegisteredUser],
    summary="Список всех зарегистрированных пользователей (только ADMIN)",
)
async def admin_get_registered_users(
    session: AsyncSession = Depends(get_session),
    requester_id: uuid.UUID = Depends(get_current_user_id),
    filters: AdminUserListFilters = Depends(),
) -> list[AdminRegisteredUser]:
    err, users = await admin_list_registered_users(
        session,
        requester_id=requester_id,
        filters=filters,
    )
    if err == "not_admin":
        raise HTTPException(
            status_code=403,
            detail="Только ADMIN может смотреть список пользователей.",
        )
    return [AdminRegisteredUser.model_validate(user) for user in users]


@app.post(
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


@app.post(
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
        raise HTTPException(status_code=502, detail="Не удалось загрузить страницу турнира.")
    if err == "parse_failed":
        raise HTTPException(
            status_code=422,
            detail="Не удалось распарсить туры/игроков из страницы турнира.",
        )
    assert result is not None
    return result


@app.patch(
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
        raise HTTPException(status_code=422, detail="Данные выбранного тура/стола повреждены.")
    assert lobby is not None
    return lobby


@app.get(
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


@app.get(
    "/lobbies",
    tags=["lobbies"],
    response_model=list[GameLobbyPublic],
    summary="Лобби, созданные текущим пользователем",
)
async def get_my_lobbies(
    session: AsyncSession = Depends(get_session),
    current_user_id: uuid.UUID = Depends(get_current_user_id),
    filters: LobbyListFilters = Depends(),
) -> list[GameLobbyPublic]:
    return await list_lobbies_for_host(session, current_user_id, filters=filters)


@app.get(
    "/lobbies/count",
    tags=["lobbies"],
    response_model=LobbiesTotalResponse,
    summary="Сколько лобби создано текущим пользователем",
)
async def get_lobbies_count(
    session: AsyncSession = Depends(get_session),
    current_user_id: uuid.UUID = Depends(get_current_user_id),
    filters: LobbyListFilters = Depends(),
) -> LobbiesTotalResponse:
    total = await count_game_lobbies(session, host_user_id=current_user_id, filters=filters)
    return LobbiesTotalResponse(total=total)


@app.get(
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
    _set_no_cache_headers(response)
    lobby = await get_lobby_with_players(session, lobby_id, viewer_user_id=current_user_id)
    if lobby is None:
        raise HTTPException(status_code=404, detail="Лобби не найдено")
    return lobby


@app.delete(
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


@app.get(
    "/lobbies/{lobby_id}/overlay-state",
    tags=["lobbies", "overlay"],
    response_model=LobbyOverlayStateResponse,
    summary="Состояние лобби для OBS overlay (только нужные поля, порядок по местам)",
)
async def get_lobby_overlay_state_endpoint(
    lobby_id: uuid.UUID,
    response: Response,
    session: AsyncSession = Depends(get_session),
    current_user_id: uuid.UUID = Depends(get_current_user_id),
) -> LobbyOverlayStateResponse:
    _set_no_cache_headers(response)
    result = await get_lobby_overlay_state(
        session,
        lobby_id,
        viewer_user_id=current_user_id,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Лобби не найдено")
    return result


@app.get(
    "/overlay/{overlay_design}/{overlay_public_id}",
    tags=["overlay"],
    response_model=LobbyOverlayStateResponse,
    summary="Состояние overlay по публичному id (и опционально lobby_id)",
)
async def get_overlay_state_by_public_id(
    overlay_design: OverlayDesign,
    overlay_public_id: uuid.UUID,
    response: Response,
    lobby_id: uuid.UUID | None = Query(
        default=None,
        description="Опционально: если передан, состояние вернётся только для этого lobby_id.",
    ),
    session: AsyncSession = Depends(get_session),
) -> LobbyOverlayStateResponse:
    _set_no_cache_headers(response)
    result = await get_lobby_overlay_state_by_public_id(
        session,
        overlay_public_id,
        expected_lobby_id=lobby_id,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Лобби для overlay не найдено")
    # Параметр дизайна в URL поддерживаем для совместимости с фронт-маршрутом.
    # Истинный выбранный дизайн всегда берём из БД.
    _ = overlay_design
    return result


@app.get(
    "/overlay/design-catalog",
    tags=["overlay"],
    response_model=OverlayDesignCatalogResponse,
    summary="Каталог дизайнов overlay для текущего пользователя",
)
async def get_overlay_design_catalog(
    session: AsyncSession = Depends(get_session),
    current_user_id: uuid.UUID = Depends(get_current_user_id),
) -> OverlayDesignCatalogResponse:
    result = await get_overlay_design_catalog_for_user(session, current_user_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return result


@app.patch(
    "/overlay/active-lobby",
    tags=["overlay"],
    response_model=ActiveOverlayLobbyResponse,
    summary="Сделать лобби активным для OBS live-ссылки",
)
async def patch_active_overlay_lobby(
    body: SetActiveOverlayLobbyBody,
    session: AsyncSession = Depends(get_session),
    acting_user_id: uuid.UUID = Depends(get_current_user_id),
) -> ActiveOverlayLobbyResponse:
    try:
        lobby_id = uuid.UUID(body.lobby_id.strip())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Некорректный lobby_id (ожидается UUID).") from exc
    err, result = await set_active_overlay_lobby(session, acting_user_id, lobby_id)
    if err == "lobby_not_found":
        raise HTTPException(status_code=404, detail="Лобби не найдено")
    if err == "not_host":
        raise HTTPException(
            status_code=403,
            detail="Активировать лобби для OBS может только хост.",
        )
    if err == "user_not_found":
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    assert result is not None
    return result


@app.get(
    "/overlay/state",
    tags=["overlay"],
    response_model=OverlayLiveStateResponse,
    summary="Текущее active-lobby состояние для OBS (по текущему пользователю)",
)
async def get_overlay_state(
    session: AsyncSession = Depends(get_session),
    acting_user_id: uuid.UUID = Depends(get_current_user_id),
) -> OverlayLiveStateResponse:
    err, result = await get_active_overlay_state_for_user(session, acting_user_id)
    if err == "user_not_found":
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    assert result is not None
    return result


@app.get(
    "/overlay/live",
    tags=["overlay"],
    response_model=OverlayLiveStateResponse,
    summary="Стабильная live-ссылка для OBS (один URL)",
)
async def get_overlay_live(
    session: AsyncSession = Depends(get_session),
    acting_user_id: uuid.UUID = Depends(get_current_user_id),
) -> OverlayLiveStateResponse:
    err, result = await get_active_overlay_state_for_user(session, acting_user_id)
    if err == "user_not_found":
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    assert result is not None
    return result


@app.get(
    "/lobbies/{lobby_id}/overlay-designs",
    tags=["lobbies", "overlay"],
    response_model=LobbyOverlayDesignsResponse,
    summary="Доступные дизайны карточек overlay для лобби",
)
async def get_lobby_overlay_designs(
    lobby_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current_user_id: uuid.UUID = Depends(get_current_user_id),
) -> LobbyOverlayDesignsResponse:
    result = await get_overlay_design_options(
        session,
        lobby_id,
        viewer_user_id=current_user_id,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Лобби не найдено")
    return result


@app.patch(
    "/lobbies/{lobby_id}/overlay-design",
    tags=["lobbies", "overlay"],
    response_model=GameLobbyPublic,
    summary="Выбрать дизайн карточек overlay для всего лобби (только хост)",
)
async def patch_lobby_overlay_design(
    lobby_id: uuid.UUID,
    body: SetOverlayDesignBody,
    session: AsyncSession = Depends(get_session),
    acting_user_id: uuid.UUID = Depends(get_current_user_id),
) -> GameLobbyPublic:
    err, lobby = await set_lobby_overlay_design(
        session, lobby_id, body.overlay_design, acting_user_id
    )
    if err == "lobby_not_found":
        raise HTTPException(status_code=404, detail="Лобби не найдено")
    if err == "not_host":
        raise HTTPException(
            status_code=403,
            detail="Менять дизайн overlay может только хост лобби.",
        )
    if err == "host_not_found":
        raise HTTPException(status_code=404, detail="Хост лобби не найден")
    if err == "unknown_design":
        raise HTTPException(status_code=404, detail="Дизайн overlay не найден")
    if err == "subscription_required":
        raise HTTPException(
            status_code=403,
            detail="Этот дизайн недоступен для текущей подписки хоста.",
        )
    assert lobby is not None
    return lobby


@app.patch(
    "/lobbies/{lobby_id}/overlay-screen",
    tags=["lobbies", "overlay"],
    response_model=GameLobbyPublic,
    summary="Переключить активный экран для OBS в рамках лобби (только хост)",
)
async def patch_lobby_overlay_screen(
    lobby_id: uuid.UUID,
    body: SetActiveOverlayScreenBody,
    session: AsyncSession = Depends(get_session),
    acting_user_id: uuid.UUID = Depends(get_current_user_id),
) -> GameLobbyPublic:
    err, lobby = await set_lobby_active_overlay_screen(
        session, lobby_id, body.screen_key, acting_user_id
    )
    if err == "lobby_not_found":
        raise HTTPException(status_code=404, detail="Лобби не найдено")
    if err == "not_host":
        raise HTTPException(
            status_code=403,
            detail="Переключать экран overlay может только хост лобби.",
        )
    assert lobby is not None
    return lobby


@app.patch(
    "/lobbies/{lobby_id}/sheriff-check",
    tags=["lobbies", "overlay"],
    response_model=GameLobbyPublic,
    summary="Обновить sheriff_check (5 значений), только хост",
)
async def patch_lobby_sheriff_check(
    lobby_id: uuid.UUID,
    body: SetSheriffCheckBody,
    session: AsyncSession = Depends(get_session),
    acting_user_id: uuid.UUID = Depends(get_current_user_id),
) -> GameLobbyPublic:
    err, lobby = await set_lobby_sheriff_check(
        session, lobby_id, body.sheriff_check, acting_user_id
    )
    if err == "lobby_not_found":
        raise HTTPException(status_code=404, detail="Лобби не найдено")
    if err == "not_host":
        raise HTTPException(
            status_code=403,
            detail="Менять sheriff_check может только хост лобби.",
        )
    assert lobby is not None
    return lobby


@app.delete(
    "/lobbies/{lobby_id}/sheriff-check",
    tags=["lobbies", "overlay"],
    response_model=GameLobbyPublic,
    summary="Сбросить sheriff_check, только хост",
)
async def delete_lobby_sheriff_check(
    lobby_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    acting_user_id: uuid.UUID = Depends(get_current_user_id),
) -> GameLobbyPublic:
    err, lobby = await clear_lobby_sheriff_check(session, lobby_id, acting_user_id)
    if err == "lobby_not_found":
        raise HTTPException(status_code=404, detail="Лобби не найдено")
    if err == "not_host":
        raise HTTPException(
            status_code=403,
            detail="Сбрасывать sheriff_check может только хост лобби.",
        )
    assert lobby is not None
    return lobby


@app.patch(
    "/lobbies/{lobby_id}/best-move",
    tags=["lobbies", "overlay"],
    response_model=GameLobbyPublic,
    summary="Обновить best_move (3 значения), только хост",
)
async def patch_lobby_best_move(
    lobby_id: uuid.UUID,
    body: SetBestMoveBody,
    session: AsyncSession = Depends(get_session),
    acting_user_id: uuid.UUID = Depends(get_current_user_id),
) -> GameLobbyPublic:
    err, lobby = await set_lobby_best_move(
        session, lobby_id, body.best_move, acting_user_id
    )
    if err == "lobby_not_found":
        raise HTTPException(status_code=404, detail="Лобби не найдено")
    if err == "not_host":
        raise HTTPException(
            status_code=403,
            detail="Менять best_move может только хост лобби.",
        )
    assert lobby is not None
    return lobby


@app.delete(
    "/lobbies/{lobby_id}/best-move",
    tags=["lobbies", "overlay"],
    response_model=GameLobbyPublic,
    summary="Сбросить best_move, только хост",
)
async def delete_lobby_best_move(
    lobby_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    acting_user_id: uuid.UUID = Depends(get_current_user_id),
) -> GameLobbyPublic:
    err, lobby = await clear_lobby_best_move(session, lobby_id, acting_user_id)
    if err == "lobby_not_found":
        raise HTTPException(status_code=404, detail="Лобби не найдено")
    if err == "not_host":
        raise HTTPException(
            status_code=403,
            detail="Сбрасывать best_move может только хост лобби.",
        )
    assert lobby is not None
    return lobby


@app.post(
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


@app.post(
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


@app.patch(
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


@app.delete(
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


@app.patch(
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


def _raise_lobby_host_mutation_error(err: str | None) -> None:
    if err == "lobby_not_found":
        raise HTTPException(status_code=404, detail="Лобби не найдено")
    if err == "not_host":
        raise HTTPException(
            status_code=403,
            detail="Менять роли и статусы может только хост лобби.",
        )
    if err == "membership_not_found":
        raise HTTPException(
            status_code=404,
            detail="Место не найдено в этом лобби.",
        )


@app.patch(
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
    _raise_lobby_host_mutation_error(err)
    assert lobby is not None
    return lobby


@app.delete(
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
    _raise_lobby_host_mutation_error(err)
    assert lobby is not None
    return lobby


@app.delete(
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


@app.patch(
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
    _raise_lobby_host_mutation_error(err)
    assert lobby is not None
    return lobby


@app.delete(
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
    _raise_lobby_host_mutation_error(err)
    assert lobby is not None
    return lobby


@app.patch(
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
    _raise_lobby_host_mutation_error(err)
    assert lobby is not None
    return lobby


@app.delete(
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
    _raise_lobby_host_mutation_error(err)
    assert lobby is not None
    return lobby


@app.delete(
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


@app.patch(
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
    _raise_lobby_host_mutation_error(err)
    assert lobby is not None
    return lobby


@app.delete(
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
    _raise_lobby_host_mutation_error(err)
    assert lobby is not None
    return lobby


@app.get("/", tags=["system"])
def root() -> dict[str, str]:
    return {"message": "Plashki API"}


_upload_dir = Path(settings.upload_dir)
if not _upload_dir.is_absolute():
    _upload_dir = Path.cwd() / _upload_dir
_upload_dir.mkdir(parents=True, exist_ok=True)
app.mount(
    "/files",
    StaticFiles(directory=str(_upload_dir)),
    name="files",
)

if settings.expose_openapi:
    _CSRF_SAFE_METHODS = frozenset({"get", "head", "options", "trace"})

    def _openapi_with_csrf_header() -> dict:
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title,
            version=app.version,
            openapi_version=app.openapi_version,
            description=app.description,
            routes=app.routes,
        )
        param = {
            "name": settings.csrf_header_name,
            "in": "header",
            "required": False,
            "schema": {"type": "string"},
        }
        for path_item in schema.get("paths", {}).values():
            if not isinstance(path_item, dict):
                continue
            for method, operation in path_item.items():
                if method in _CSRF_SAFE_METHODS or not isinstance(operation, dict):
                    continue
                params = operation.setdefault("parameters", [])
                if not any(
                    p.get("name") == settings.csrf_header_name and p.get("in") == "header"
                    for p in params
                    if isinstance(p, dict)
                ):
                    params.append(param)
        app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = _openapi_with_csrf_header  # type: ignore[method-assign]
