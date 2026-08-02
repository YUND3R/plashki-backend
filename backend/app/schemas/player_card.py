import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.public_media import PublicMediaResponseMixin

MAX_PLAYER_CARD_PHOTOS = 10


class PlayerCardWrite(BaseModel):
    first_name: str = Field(max_length=100)
    last_name: str = Field(max_length=100)
    nickname: str = Field(max_length=255)
    club: str | None = Field(default=None, max_length=255)
    gomafia_url: str | None = Field(default=None, max_length=512)
    photo_urls: list[str] = Field(default_factory=list)

    @field_validator("photo_urls")
    @classmethod
    def validate_photos(cls, v: list[str]) -> list[str]:
        if len(v) > MAX_PLAYER_CARD_PHOTOS:
            raise ValueError(f"Не больше {MAX_PLAYER_CARD_PHOTOS} фото")
        for url in v:
            if len(url) > 2048:
                raise ValueError("URL фото слишком длинный")
        return v


class PlayerCardPatch(BaseModel):
    first_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    nickname: str | None = Field(default=None, max_length=255)
    club: str | None = Field(default=None, max_length=255)
    gomafia_url: str | None = Field(default=None, max_length=512)
    photo_urls: list[str] | None = Field(default=None)

    @field_validator("photo_urls")
    @classmethod
    def validate_photos(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        if len(v) > MAX_PLAYER_CARD_PHOTOS:
            raise ValueError(f"Не больше {MAX_PLAYER_CARD_PHOTOS} фото")
        for url in v:
            if len(url) > 2048:
                raise ValueError("URL фото слишком длинный")
        return v


class PlayerCardPhotoResponse(PublicMediaResponseMixin, BaseModel):
    """Ответ после загрузки файла в карточку: URL файла и актуальный список photo_urls."""

    url: str
    photo_urls: list[str]


class PlayerCardPublic(PublicMediaResponseMixin, BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_user_id: uuid.UUID
    first_name: str
    last_name: str
    nickname: str
    club: str | None
    gomafia_url: str | None
    photo_urls: list[str]
    created_at: datetime
    updated_at: datetime
