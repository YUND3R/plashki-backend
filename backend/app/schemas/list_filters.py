from typing import Literal

from pydantic import BaseModel, Field

from app.db.base import OverlayDesign, Role, Subscription


class ListPaginationParams(BaseModel):
    limit: int | None = Field(default=None, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class LobbyListFilters(ListPaginationParams):
    q: str | None = Field(default=None, max_length=120)
    overlay_design: OverlayDesign | None = None
    sort_by: Literal["created_at", "title", "max_players"] = "created_at"
    sort_order: Literal["asc", "desc"] = "desc"


class PlayerCardListFilters(ListPaginationParams):
    q: str | None = Field(
        default=None,
        max_length=255,
        description="Поиск по nickname, имени, фамилии, клубу и ссылке gomafia.",
    )
    has_photos: bool | None = None
    sort_by: Literal["created_at", "updated_at", "nickname"] = "created_at"
    sort_order: Literal["asc", "desc"] = "asc"


class AdminUserListFilters(ListPaginationParams):
    q: str | None = Field(default=None, max_length=255)
    role: Role | None = None
    subscription: Subscription | None = None
    sort_by: Literal["created_at", "username", "email"] = "created_at"
    sort_order: Literal["asc", "desc"] = "asc"
