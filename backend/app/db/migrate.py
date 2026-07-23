"""Safe migration entrypoint for fresh and legacy databases."""

import asyncio
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings
ROOT = Path(__file__).resolve().parents[2]
BASELINE_REVISION = "20260724_01"
NORMALIZED_REVISION = "20260724_02"

LEGACY_SIGNATURE = {
    "user_profile": {
        "id",
        "subscription",
        "subscription_until",
        "active_overlay_lobby_id",
    },
    "game_lobby": {
        "id",
        "overlay_public_id",
        "selected_overlay_design",
        "active_overlay_screen",
        "show_victory_scores",
        "sheriff_check",
        "best_move",
    },
    "lobby_membership": {"id", "lobby_id", "player_card_id"},
    "pending_registration": {"id", "username", "email"},
    "player_card": {"id", "owner_user_id"},
    "password_reset_token": {"id", "user_id"},
    "email_verification_token": {"id", "user_id", "pending_registration_id"},
    "feedback_message": {"id", "user_id"},
    "user_overlay_design_access": {"id", "user_id", "design_code"},
}
NORMALIZED_SIGNATURE = {
    "user_profile": {"id"},
    "game_lobby": {"id"},
    "broadcast_user_settings": {"user_id", "active_overlay_lobby_id"},
    "lobby_overlay_state": {
        "lobby_id",
        "overlay_public_id",
        "selected_overlay_design",
        "active_overlay_screen",
        "show_victory_scores",
        "sheriff_check",
        "best_move",
    },
    "commerce_user_subscription": {
        "user_id",
        "subscription",
        "subscription_until",
    },
    "lobby_membership": {"id", "lobby_id", "player_card_id"},
    "pending_registration": {"id", "username", "email"},
    "player_card": {"id", "owner_user_id"},
    "password_reset_token": {"id", "user_id"},
    "email_verification_token": {"id", "user_id", "pending_registration_id"},
    "feedback_message": {"id", "user_id"},
    "user_overlay_design_access": {"id", "user_id", "design_code"},
}


def _alembic_config(
    database_url: str | None = None, schema: str | None = None
) -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.attributes["database_url"] = database_url or settings.database_url
    if schema:
        config.attributes["schema"] = schema
    return config


async def _inspect_schema(
    database_url: str | None = None, schema: str | None = None
) -> tuple[bool, str, list[str]]:
    url = database_url or settings.database_url
    if not url:
        raise RuntimeError("DATABASE_URL is required for migrations")
    connect_args = (
        {"server_settings": {"search_path": schema}} if schema is not None else {}
    )
    engine = create_async_engine(url, pool_pre_ping=True, connect_args=connect_args)

    def inspect_sync(connection) -> tuple[bool, str, list[str]]:
        inspector = inspect(connection)
        existing_tables = set(inspector.get_table_names())
        versioned = "alembic_version" in existing_tables

        def signature_problems(signature: dict[str, set[str]]) -> list[str]:
            problems: list[str] = []
            for table_name, required_columns in signature.items():
                if table_name not in existing_tables:
                    problems.append(f"missing table {table_name}")
                    continue
                actual = {
                    column["name"] for column in inspector.get_columns(table_name)
                }
                for column_name in sorted(required_columns - actual):
                    problems.append(f"missing column {table_name}.{column_name}")
            return problems

        app_tables = {
            "user_profile",
            "pending_registration",
            "player_card",
            "game_lobby",
            "lobby_membership",
            "password_reset_token",
            "email_verification_token",
            "feedback_message",
            "user_overlay_design_access",
            "broadcast_user_settings",
            "lobby_overlay_state",
            "commerce_user_subscription",
        }
        if not (app_tables & existing_tables):
            return versioned, "empty", []
        normalized_problems = signature_problems(NORMALIZED_SIGNATURE)
        if not normalized_problems:
            return versioned, "normalized", []
        legacy_problems = signature_problems(LEGACY_SIGNATURE)
        if not legacy_problems:
            return versioned, "legacy", []
        return versioned, "unknown", sorted(set(legacy_problems + normalized_problems))

    try:
        async with engine.connect() as connection:
            return await connection.run_sync(inspect_sync)
    finally:
        await engine.dispose()


def migrate(database_url: str | None = None, schema: str | None = None) -> None:
    config = _alembic_config(database_url, schema)
    versioned, state, problems = asyncio.run(
        _inspect_schema(database_url, schema)
    )
    if not versioned and state == "unknown":
        details = ", ".join(problems)
        raise RuntimeError(
            "Refusing to stamp an unrecognized or incomplete schema; "
            f"manual migration is required ({details})."
        )
    if not versioned and state == "legacy":
        command.stamp(config, BASELINE_REVISION)
    elif not versioned and state == "normalized":
        command.stamp(config, NORMALIZED_REVISION)
    command.upgrade(config, "head")


if __name__ == "__main__":
    migrate()
