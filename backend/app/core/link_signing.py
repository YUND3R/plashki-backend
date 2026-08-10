"""HMAC-подписи для одноразовых ссылок (email / сброс пароля). Сырой секрет в URL не передаётся."""

from __future__ import annotations

import hashlib
import hmac
import uuid
from datetime import datetime, timezone

from app.core.config import settings


def _signing_key() -> bytes:
    raw = settings.jwt_secret_key.strip()
    if raw:
        return raw.encode("utf-8")
    if settings.environment == "local":
        return b"local-only-plashki-jwt-secret-min-32-chars!!"
    raise RuntimeError("JWT_SECRET_KEY обязателен для подписи ссылок вне local")


def _exp_ts(expires_at: datetime) -> int:
    exp = expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    return int(exp.timestamp())


def sign_email_verification(token_id: uuid.UUID, user_id: uuid.UUID, expires_at: datetime) -> str:
    msg = f"ev:{token_id}:{user_id}:{_exp_ts(expires_at)}".encode("ascii")
    return hmac.new(_signing_key(), msg, hashlib.sha256).hexdigest()


def sign_email_verification_pending(
    token_id: uuid.UUID,
    pending_id: uuid.UUID,
    expires_at: datetime,
) -> str:
    msg = f"evp:{token_id}:{pending_id}:{_exp_ts(expires_at)}".encode("ascii")
    return hmac.new(_signing_key(), msg, hashlib.sha256).hexdigest()


def sign_password_reset(token_id: uuid.UUID, user_id: uuid.UUID, expires_at: datetime) -> str:
    msg = f"pr:{token_id}:{user_id}:{_exp_ts(expires_at)}".encode("ascii")
    return hmac.new(_signing_key(), msg, hashlib.sha256).hexdigest()


def sign_email_change(token_id: uuid.UUID, user_id: uuid.UUID, expires_at: datetime) -> str:
    msg = f"ec:{token_id}:{user_id}:{_exp_ts(expires_at)}".encode("ascii")
    return hmac.new(_signing_key(), msg, hashlib.sha256).hexdigest()


def verify_email_hmac(
    token_id: uuid.UUID,
    user_id: uuid.UUID,
    expires_at: datetime,
    signature_hex: str,
) -> bool:
    expected = sign_email_verification(token_id, user_id, expires_at)
    try:
        return hmac.compare_digest(expected, signature_hex.strip().lower())
    except (TypeError, ValueError):
        return False


def verify_password_reset_hmac(
    token_id: uuid.UUID,
    user_id: uuid.UUID,
    expires_at: datetime,
    signature_hex: str,
) -> bool:
    expected = sign_password_reset(token_id, user_id, expires_at)
    try:
        return hmac.compare_digest(expected, signature_hex.strip().lower())
    except (TypeError, ValueError):
        return False


def verify_email_change_hmac(
    token_id: uuid.UUID,
    user_id: uuid.UUID,
    expires_at: datetime,
    signature_hex: str,
) -> bool:
    expected = sign_email_change(token_id, user_id, expires_at)
    try:
        return hmac.compare_digest(expected, signature_hex.strip().lower())
    except (TypeError, ValueError):
        return False


def verify_email_hmac_pending(
    token_id: uuid.UUID,
    pending_id: uuid.UUID,
    expires_at: datetime,
    signature_hex: str,
) -> bool:
    expected = sign_email_verification_pending(token_id, pending_id, expires_at)
    try:
        return hmac.compare_digest(expected, signature_hex.strip().lower())
    except (TypeError, ValueError):
        return False
