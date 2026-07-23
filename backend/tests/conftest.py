import asyncio
import os
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _async_postgres_url(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


@pytest.fixture(scope="session")
def test_database_url() -> str:
    raw_url = os.getenv("TEST_DATABASE_URL", "").strip()
    if not raw_url:
        pytest.skip("TEST_DATABASE_URL is not set; PostgreSQL integration tests are opt-in")
    return _async_postgres_url(raw_url)


@pytest.fixture
def postgres_schema(test_database_url: str):
    schema = f"pytest_{uuid.uuid4().hex}"
    # pytest uses separate asyncio.run() loops; never reuse asyncpg connections
    # across those loops.
    engine = create_async_engine(test_database_url, poolclass=NullPool)

    async def create_schema() -> None:
        async with engine.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))

    async def drop_schema() -> None:
        async with engine.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await engine.dispose()

    asyncio.run(create_schema())
    try:
        yield schema
    finally:
        asyncio.run(drop_schema())
