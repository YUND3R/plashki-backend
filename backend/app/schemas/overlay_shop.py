import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.db.base import OverlayDesign


class OverlayDesignShopItem(BaseModel):
    code: OverlayDesign
    title: str
    price_rub: int
    rental_hours: int
    animations_supported: bool
    selectable: bool
    access_expires_at: datetime | None = None
    access_unlimited: bool = False


class OverlayDesignShopCatalogResponse(BaseModel):
    items: list[OverlayDesignShopItem]


class UserOverlayDesignAccessPublic(BaseModel):
    design_code: OverlayDesign
    title: str
    price_rub: int
    rental_hours: int
    expires_at: datetime
    is_active: bool


class UserOverlayDesignAccessListResponse(BaseModel):
    items: list[UserOverlayDesignAccessPublic]


class GrantOverlayDesignAccessBody(BaseModel):
    design_code: OverlayDesign = Field(description="Код плашки (plus, classic, masters-yug25).")


class GrantOverlayDesignAccessResponse(BaseModel):
    user_id: uuid.UUID
    design_code: OverlayDesign
    expires_at: datetime
    price_rub: int
    rental_hours: int
