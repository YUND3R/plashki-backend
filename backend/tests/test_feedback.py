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
