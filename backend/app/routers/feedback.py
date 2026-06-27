import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.deps.auth import get_current_user_id
from app.schemas.feedback import FeedbackSubmittedResponse, SubmitFeedbackBody
from app.services.feedback import submit_user_feedback

router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.post(
    "",
    response_model=FeedbackSubmittedResponse,
    summary="Отправить обратную связь (авторизованный пользователь)",
)
async def post_feedback(
    body: SubmitFeedbackBody,
    session: AsyncSession = Depends(get_session),
    user_id: uuid.UUID = Depends(get_current_user_id),
) -> FeedbackSubmittedResponse:
    result = await submit_user_feedback(session, user_id=user_id, body=body)
    if result is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return result
