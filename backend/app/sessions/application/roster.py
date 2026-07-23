from dataclasses import dataclass
from typing import Protocol
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PlayerCard


@dataclass(frozen=True, slots=True)
class RosterCard:
    id: uuid.UUID
    owner_user_id: uuid.UUID
    photo_urls: frozenset[str]


class RosterPort(Protocol):
    async def get_card(self, card_id: uuid.UUID) -> RosterCard | None: ...


class SqlAlchemyRoster:
    """Adapter isolating Sessions use cases from roster persistence details."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_card(self, card_id: uuid.UUID) -> RosterCard | None:
        card = await self.session.get(PlayerCard, card_id)
        if card is None:
            return None
        return RosterCard(
            id=card.id,
            owner_user_id=card.owner_user_id,
            photo_urls=frozenset(
                url.strip()
                for url in card.photo_urls or []
                if isinstance(url, str) and url.strip()
            ),
        )
