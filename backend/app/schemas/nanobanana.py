from pydantic import BaseModel, Field

from app.schemas.public_media import PublicMediaResponseMixin


class NanoBananaProcessResponse(PublicMediaResponseMixin, BaseModel):
    url: str
    provider: str = Field(default="nanobanana")
    output_mime: str
    size_bytes: int
