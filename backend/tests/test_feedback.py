from datetime import datetime, timezone
from types import SimpleNamespace
import uuid

from app.schemas.feedback import SubmitFeedbackBody
from app.services import feedback as feedback_service


def test_submit_feedback_returns_response(monkeypatch) -> None:
    user_id = uuid.uuid4()
    user = SimpleNamespace(id=user_id, username="host", email="host@example.com")
    class FakeSession:
        def __init__(self):
            self.row_id = uuid.uuid4()
            self.commit_called = False
            self.saved = None

        async def get(self, _model, ident):
            assert ident == user_id
            return user

        def add(self, row):
            self.saved = row

        async def commit(self):
            self.commit_called = True

        async def refresh(self, row):
            row.created_at = datetime.now(timezone.utc)

    session = FakeSession()

    class FakeFeedback:
        def __init__(self, **kwargs):
            self.id = session.row_id
            self.user_id = kwargs["user_id"]
            self.category = kwargs["category"]
            self.message = kwargs["message"]
            self.page_url = kwargs.get("page_url")
            self.contact_email = kwargs.get("contact_email")
            self.created_at = datetime.now(timezone.utc)

    monkeypatch.setattr(feedback_service, "FeedbackMessage", FakeFeedback)
    monkeypatch.setattr(feedback_service, "_notify_team", lambda **_kwargs: None)
    monkeypatch.setattr(feedback_service, "_notify_user_ack", lambda **_kwargs: None)

    import asyncio

    result = asyncio.run(
        feedback_service.submit_user_feedback(
            session,  # type: ignore[arg-type]
            user_id=user_id,
            body=SubmitFeedbackBody(
                category="bug",
                message="Кнопка OBS не переключает экран",
                page_url="http://localhost:5173/lobby/manage",
            ),
        )
    )

    assert result is not None
    assert result.id == session.row_id
    assert session.commit_called is True
    assert "Спасибо" in result.detail


def test_notify_user_ack_uses_contact_email_or_profile_email(monkeypatch) -> None:
    sent_to: list[str] = []

    def _fake_send_email(*, to_email: str, subject: str, body: str, html_body=None) -> bool:
        _ = subject
        _ = body
        _ = html_body
        sent_to.append(to_email)
        return True

    monkeypatch.setattr(feedback_service.alert_service, "send_email", _fake_send_email)

    user = SimpleNamespace(username="host", email="host@example.com")
    feedback_with_contact = SimpleNamespace(category="idea", message="msg", contact_email="contact@example.com")
    feedback_without_contact = SimpleNamespace(category="idea", message="msg", contact_email=None)

    feedback_service._notify_user_ack(user=user, feedback=feedback_with_contact)
    feedback_service._notify_user_ack(user=user, feedback=feedback_without_contact)

    assert sent_to == ["contact@example.com", "host@example.com"]
