"""One-off: переписать сохранённые URL файлов на текущий PUBLIC_BASE_URL.

Пример на сервере:
  PUBLIC_BASE_URL=https://api.plash-ki.ru python -m scripts.rewrite_media_urls
"""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.db.models import LobbyMembership, PendingRegistration, PlayerCard, UserProfile
from app.media.public_urls import rewrite_public_file_url, rewrite_public_file_urls


def _require_public_base_url() -> str:
    base = settings.public_base_url.strip().rstrip("/")
    if not base:
        print("Задай PUBLIC_BASE_URL в .env (например https://api.plash-ki.ru).", file=sys.stderr)
        raise SystemExit(1)
    return base


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


async def main() -> None:
    base = _require_public_base_url()
    if settings.database_url is None:
        print("DATABASE_URL не задан.", file=sys.stderr)
        raise SystemExit(1)

    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

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

    await engine.dispose()

    total = sum(counts.values())
    print(f"PUBLIC_BASE_URL={base}")
    for label, count in counts.items():
        print(f"{label}: {count}")
    print(f"total rows updated: {total}")


if __name__ == "__main__":
    asyncio.run(main())
