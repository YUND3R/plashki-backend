import asyncio
import uuid
from unittest.mock import AsyncMock

import pytest

from app.core.password import hash_password
from app.db.models import PasswordResetToken, UserProfile
from app.services import password_reset as password_reset_service


def test_reset_password_by_signed_increments_token_version(monkeypatch: pytest.MonkeyPatch) -> None:
    user = UserProfile(
        id=uuid.uuid4(),
        username="user1",
        email="user1@example.com",
        nickname="user1",
        hashed_password=hash_password("old-password"),
        token_version=0,
    )
    token_row = PasswordResetToken(
        id=uuid.uuid4(),
        user_id=user.id,
        token_hash=None,
        expires_at=password_reset_service._expires_at(),
    )
    session = AsyncMock()
    session.get = AsyncMock(side_effect=lambda model, obj_id: {
        token_row.id: token_row,
        user.id: user,
    }.get(obj_id))
    monkeypatch.setattr(
        password_reset_service,
        "verify_password_reset_hmac",
        lambda *_args, **_kwargs: True,
    )

    result = asyncio.run(
        password_reset_service.reset_password_by_signed(
            session,
            token_id=token_row.id,
            signature="a" * 64,
            new_password="new-password-1",
        )
    )

    assert result == ("ok", user)
    assert user.token_version == 1
    session.commit.assert_awaited()
