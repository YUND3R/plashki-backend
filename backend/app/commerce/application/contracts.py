from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
import uuid

from app.db.base import OverlayDesign


@dataclass(frozen=True, slots=True)
class OverlayDesignOption:
    code: OverlayDesign
    title: str
    price_rub: int
    rental_hours: int
    animations_supported: bool
    selectable: bool
    access_expires_at: datetime | None = None
    access_unlimited: bool = False


class OverlayDesignAccessPort(Protocol):
    async def options_for_user(
        self, user_id: uuid.UUID | None
    ) -> list[OverlayDesignOption]: ...

    async def can_use(self, user_id: uuid.UUID, design: OverlayDesign) -> bool: ...

    async def host_has_access(
        self, host_user_id: uuid.UUID | None, design: OverlayDesign
    ) -> bool: ...
