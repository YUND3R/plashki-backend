import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import FeedbackMessage, UserProfile
from app.notifications.application import NotificationFacade
from app.notifications.providers import get_notification_facade
from app.schemas.feedback import FeedbackCategory, FeedbackSubmittedResponse, SubmitFeedbackBody

alert_service = get_notification_facade()


def _category_label(category: FeedbackCategory) -> str:
    labels = {"bug": "Баг", "idea": "Идея", "other": "Другое"}
    return labels.get(category, category)


async def submit_user_feedback(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    body: SubmitFeedbackBody,
    notifications: NotificationFacade | None = None,
) -> FeedbackSubmittedResponse | None:
    user = await session.get(UserProfile, user_id)
    if user is None:
        return None

    clean_message = body.message.strip()
    row = FeedbackMessage(
        user_id=user_id,
        category=body.category,
        message=clean_message,
        page_url=(body.page_url or "").strip() or None,
        contact_email=(body.contact_email or "").strip() or None,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)

    facade = notifications or alert_service
    _notify_team(user=user, feedback=row, notifications=facade)
    _notify_user_ack(user=user, feedback=row, notifications=facade)
    return FeedbackSubmittedResponse(id=row.id, created_at=row.created_at)


def _notify_team(
    *,
    user: UserProfile,
    feedback: FeedbackMessage,
    notifications: NotificationFacade = alert_service,
) -> None:
    category = _category_label(feedback.category)  # type: ignore[arg-type]
    contact = feedback.contact_email or user.email
    page = feedback.page_url or "—"
    text = (
        f"[Plashki feedback] {category}\n"
        f"User: {user.username} ({user.email})\n"
        f"Contact: {contact}\n"
        f"Page: {page}\n\n"
        f"{feedback.message}"
    )

    notifications.send_telegram(text)

    subject = f"[Plashki] Обратная связь: {category} от {user.username}"
    body = (
        f"Категория: {category}\n"
        f"Пользователь: {user.username} ({user.email})\n"
        f"Контакт: {contact}\n"
        f"Страница: {page}\n\n"
        f"{feedback.message}"
    )
    for email in notifications.alert_recipients():
        notifications.send_email(to_email=email, subject=subject, body=body)


def _notify_user_ack(
    *,
    user: UserProfile,
    feedback: FeedbackMessage,
    notifications: NotificationFacade = alert_service,
) -> None:
    to_email = (feedback.contact_email or "").strip() or user.email
    if not to_email:
        return
    subject = "[Plashki] Мы получили ваше обращение"
    body = (
        "Спасибо! Мы получили ваше обращение и передали его в работу.\n\n"
        f"Категория: {_category_label(feedback.category)}\n"
        f"Ваш текст: {feedback.message}\n\n"
        "Если потребуется уточнение, свяжемся с вами по указанному контакту."
    )
    notifications.send_email(to_email=to_email, subject=subject, body=body)
