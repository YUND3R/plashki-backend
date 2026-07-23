import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.db.base import Base
from app.db.migrate import migrate
from app.db.session import get_session
from app.main import app


@pytest.mark.integration
def test_fresh_upgrade_is_idempotent_and_health_uses_postgres(
    test_database_url: str,
    postgres_schema: str,
) -> None:
    migrate(test_database_url, postgres_schema)
    migrate(test_database_url, postgres_schema)

    engine = create_async_engine(
        test_database_url,
        connect_args={"server_settings": {"search_path": postgres_schema}},
        poolclass=NullPool,
    )
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def verify_migration() -> None:
        async with engine.connect() as connection:
            tables = await connection.run_sync(
                lambda sync_connection: set(inspect(sync_connection).get_table_names())
            )
            revision = (
                await connection.execute(text("SELECT version_num FROM alembic_version"))
            ).scalar_one()
        assert set(Base.metadata.tables).issubset(tables)
        assert revision == "20260724_02"

    async def override_session():
        async with session_factory() as session:
            yield session

    asyncio.run(verify_migration())
    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "database": "connected"}
    finally:
        app.dependency_overrides.pop(get_session, None)
        asyncio.run(engine.dispose())


@pytest.mark.integration
def test_legacy_database_without_version_is_stamped_and_backfilled(
    test_database_url: str,
    postgres_schema: str,
) -> None:
    from alembic import command
    from alembic.config import Config

    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option(
        "script_location", str(Path(__file__).resolve().parents[1] / "migrations")
    )
    config.attributes["database_url"] = test_database_url
    config.attributes["schema"] = postgres_schema
    command.upgrade(config, "20260724_01")

    engine = create_async_engine(
        test_database_url,
        connect_args={"server_settings": {"search_path": postgres_schema}},
        poolclass=NullPool,
    )

    async def seed_legacy() -> tuple[str, str, str]:
        user_id = "11111111-1111-1111-1111-111111111111"
        lobby_id = "22222222-2222-2222-2222-222222222222"
        public_id = "33333333-3333-3333-3333-333333333333"
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    INSERT INTO user_profile (
                        id, username, email, first_name, last_name, nickname,
                        hashed_password, subscription, subscription_until
                    ) VALUES (
                        CAST(:user_id AS uuid), 'legacy', 'legacy@example.test',
                        '', '', 'legacy', 'hash', 'premium',
                        TIMESTAMPTZ '2030-01-01 00:00:00+00'
                    )
                    """
                ),
                {"user_id": user_id},
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO game_lobby (
                        id, overlay_public_id, host_user_id,
                        selected_overlay_design, active_overlay_screen,
                        show_victory_scores, sheriff_check, best_move
                    ) VALUES (
                        CAST(:lobby_id AS uuid), CAST(:public_id AS uuid),
                        CAST(:user_id AS uuid), 'plus', 'roles', true,
                        '["1"]'::jsonb, '["2"]'::jsonb
                    )
                    """
                ),
                {
                    "user_id": user_id,
                    "lobby_id": lobby_id,
                    "public_id": public_id,
                },
            )
            await connection.execute(
                text(
                    """
                    UPDATE user_profile
                    SET active_overlay_lobby_id = CAST(:lobby_id AS uuid)
                    WHERE id = CAST(:user_id AS uuid)
                    """
                ),
                {"user_id": user_id, "lobby_id": lobby_id},
            )
            await connection.execute(text("DROP TABLE alembic_version"))
        return user_id, lobby_id, public_id

    user_id, lobby_id, public_id = asyncio.run(seed_legacy())
    migrate(test_database_url, postgres_schema)

    async def verify() -> None:
        async with engine.connect() as connection:
            revision = (
                await connection.execute(text("SELECT version_num FROM alembic_version"))
            ).scalar_one()
            subscription = (
                await connection.execute(
                    text(
                        """
                        SELECT subscription
                        FROM commerce_user_subscription
                        WHERE user_id = CAST(:user_id AS uuid)
                        """
                    ),
                    {"user_id": user_id},
                )
            ).scalar_one()
            overlay = (
                await connection.execute(
                    text(
                        """
                        SELECT overlay_public_id::text, active_overlay_screen
                        FROM lobby_overlay_state
                        WHERE lobby_id = CAST(:lobby_id AS uuid)
                        """
                    ),
                    {"lobby_id": lobby_id},
                )
            ).one()
            active = (
                await connection.execute(
                    text(
                        """
                        SELECT active_overlay_lobby_id::text
                        FROM broadcast_user_settings
                        WHERE user_id = CAST(:user_id AS uuid)
                        """
                    ),
                    {"user_id": user_id},
                )
            ).scalar_one()
            columns = await connection.run_sync(
                lambda sync_connection: {
                    item["name"]
                    for item in inspect(sync_connection).get_columns("user_profile")
                }
            )
        assert revision == "20260724_02"
        assert subscription == "premium"
        assert overlay == (public_id, "roles")
        assert active == lobby_id
        assert "subscription" not in columns
        assert "active_overlay_lobby_id" not in columns

    try:
        asyncio.run(verify())
    finally:
        asyncio.run(engine.dispose())


@pytest.mark.integration
def test_normalized_database_without_version_is_safely_restamped(
    test_database_url: str,
    postgres_schema: str,
) -> None:
    migrate(test_database_url, postgres_schema)
    engine = create_async_engine(
        test_database_url,
        connect_args={"server_settings": {"search_path": postgres_schema}},
        poolclass=NullPool,
    )

    async def drop_version() -> None:
        async with engine.begin() as connection:
            await connection.execute(text("DROP TABLE alembic_version"))

    asyncio.run(drop_version())
    migrate(test_database_url, postgres_schema)
    migrate(test_database_url, postgres_schema)

    async def revision() -> str:
        async with engine.connect() as connection:
            return (
                await connection.execute(text("SELECT version_num FROM alembic_version"))
            ).scalar_one()

    try:
        assert asyncio.run(revision()) == "20260724_02"
    finally:
        asyncio.run(engine.dispose())
