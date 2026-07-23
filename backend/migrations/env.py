import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool, text
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.core.config import settings
from app.db.base import Base
from app.db import models as _models  # noqa: F401


config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    configured = config.attributes.get("database_url")
    return str(configured or settings.database_url)


def _schema() -> str | None:
    configured = config.attributes.get("schema")
    return str(configured) if configured else None


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table_schema=_schema(),
    )
    with context.begin_transaction():
        context.run_migrations()


def _run_migrations(connection) -> None:
    schema = _schema()
    if schema:
        quoted_schema = connection.dialect.identifier_preparer.quote(schema)
        connection.execute(text(f"SET search_path TO {quoted_schema}"))
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        version_table_schema=schema,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = _database_url()
    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    # Use an explicit outer transaction so PostgreSQL commits both the
    # search_path change and all transactional DDL before the connection closes.
    async with connectable.begin() as connection:
        await connection.run_sync(_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
