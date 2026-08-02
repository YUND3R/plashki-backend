"""Переписать сохранённые URL /files/* на текущий PUBLIC_BASE_URL."""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.db.models import LobbyMembership, PendingRegistration, PlayerCard, UserProfile
from app.media.public_urls import rewrite_public_file_url, rewrite_public_file_urls

logger = logging.getLogger(__name__)


async def _rewrite_avatar_column(session: AsyncSession, model, column_name: str) -> int:
    updated = 0
    rows = (await session.execute(select(model))).scalars().all()
    for row in rows:
        current = getattr(row, column_name)
        if not current:
            continue
        new_value = rewrite_public_file_url(str(current))
        if new_value and new_value != current:
            setattr(row, column_name, new_value)
            updated += 1
    return updated


async def _rewrite_player_cards(session: AsyncSession) -> int:
    updated = 0
    rows = (await session.execute(select(PlayerCard))).scalars().all()
    for row in rows:
        current = list(row.photo_urls or [])
        if not current:
            continue
        new_value = rewrite_public_file_urls(current)
        if new_value != current:
            row.photo_urls = new_value
            updated += 1
    return updated


async def _rewrite_stored_media_urls_async(
    database_url: str,
) -> dict[str, int]:
    engine = create_async_engine(database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with session_factory() as session:
            counts = {
                "user_profile.avatar_url": await _rewrite_avatar_column(
                    session, UserProfile, "avatar_url"
                ),
                "pending_registration.avatar_url": await _rewrite_avatar_column(
                    session, PendingRegistration, "avatar_url"
                ),
                "lobby_membership.lobby_photo_url": await _rewrite_avatar_column(
                    session, LobbyMembership, "lobby_photo_url"
                ),
                "player_card.photo_urls": await _rewrite_player_cards(session),
            }
            await session.commit()
            return counts
    finally:
        await engine.dispose()


def rewrite_stored_media_urls(
    database_url: str | None = None,
    *,
    required: bool = False,
) -> dict[str, int]:
    """Идемпотентно обновляет URL файлов в БД под PUBLIC_BASE_URL."""
    base = settings.public_base_url.strip().rstrip("/")
    if not base:
        message = "rewrite_media_urls: skip (PUBLIC_BASE_URL not set)"
        if required:
            raise RuntimeError(message)
        logger.info(message)
        return {}

    url = database_url or settings.database_url
    if not url:
        message = "rewrite_media_urls: skip (DATABASE_URL not set)"
        if required:
            raise RuntimeError(message)
        logger.warning(message)
        return {}

    counts = asyncio.run(_rewrite_stored_media_urls_async(url))
    total = sum(counts.values())
    logger.info(
        "rewrite_media_urls: PUBLIC_BASE_URL=%s total_rows_updated=%s details=%s",
        base,
        total,
        counts,
    )
    return counts
