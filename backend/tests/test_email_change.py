import uuid
from datetime import UTC, datetime, timedelta

from pydantic import ValidationError

from app.core.link_signing import (
    sign_email_change,
    sign_password_reset,
    verify_email_change_hmac,
)
from app.schemas.auth import ChangeEmailConfirmBody, ChangeEmailRequestBody


def test_email_change_signature_has_separate_domain() -> None:
    token_id = uuid.uuid4()
    user_id = uuid.uuid4()
    expires_at = datetime.now(UTC) + timedelta(minutes=30)
    signature = sign_email_change(token_id, user_id, expires_at)
    assert verify_email_change_hmac(token_id, user_id, expires_at, signature)
    assert signature != sign_password_reset(token_id, user_id, expires_at)


def test_email_change_confirm_requires_full_signature() -> None:
    try:
        ChangeEmailConfirmBody(token_id=uuid.uuid4(), signature="short")
    except ValidationError:
        pass
    else:
        raise AssertionError("short signature must be rejected")


def test_email_change_request_schema_limits_values() -> None:
    body = ChangeEmailRequestBody(new_email="new@example.com", current_password="password")
    assert body.new_email == "new@example.com"
