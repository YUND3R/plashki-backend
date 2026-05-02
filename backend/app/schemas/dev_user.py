import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.db.base import Role


class TestUserCreateBody(BaseModel):
    username: str = Field(
        min_length=1,
        max_length=55,
        description="Логин аккаунта (уникален). Это не игровой nickname из кабинета.",
    )
    email: str = Field(
        min_length=1,
        max_length=55,
        description="Уникальный email. 409 часто из‑за email, если username вы меняли, а email оставили старым.",
    )
    password: str = Field(min_length=1, max_length=128)
    role: Role = Field(default=Role.USER, description="Для проверки admin-ручек поставь admin.")


class TestAdminCreateBody(BaseModel):
    """Удобные дефолты для быстрого вызова из Swagger; при 409 поменяй username/email."""

    username: str = Field(default="dev_admin", min_length=1, max_length=55)
    email: str = Field(default="dev_admin@dev.local", min_length=1, max_length=55)
    password: str = Field(default="admin", min_length=1, max_length=128)


class TestUserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    email: str
    first_name: str
    last_name: str
    avatar_url: str | None = None
    nickname: str
    role: Role
    email_verified_at: datetime | None = None
