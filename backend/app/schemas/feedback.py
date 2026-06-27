import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


FeedbackCategory = Literal["bug", "idea", "other"]


class SubmitFeedbackBody(BaseModel):
    category: FeedbackCategory = Field(description="Тип обращения: bug, idea, other")
    message: str = Field(min_length=10, max_length=4000)
    page_url: str | None = Field(default=None, max_length=1024)
    contact_email: str | None = Field(default=None, max_length=255)


class FeedbackSubmittedResponse(BaseModel):
    id: uuid.UUID
    created_at: datetime
    detail: str = "Спасибо! Обратная связь отправлена."
