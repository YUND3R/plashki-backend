from pydantic import BaseModel, Field


class NanoBananaProcessResponse(BaseModel):
    url: str
    provider: str = Field(default="nanobanana")
    output_mime: str
    size_bytes: int
