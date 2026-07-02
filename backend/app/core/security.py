import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt

from app.core.config import settings

ALGORITHM = "HS256"


@dataclass(frozen=True)
class AccessTokenClaims:
    user_id: uuid.UUID
    token_version: int


def _jwt_secret() -> str:
    s = settings.jwt_secret_key.strip()
    if s:
        return s
    if settings.environment in ("local", "development"):
        return "local-only-plashki-jwt-secret-min-32-chars!!"
    raise RuntimeError("Задайте JWT_SECRET_KEY (или SECRET_KEY) в .env")


def create_access_token(*, user_id: uuid.UUID, token_version: int = 0) -> str:
    now = datetime.now(UTC)
    exp = now + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "sub": str(user_id),
        "tv": token_version,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "type": "access",
    }
    return jwt.encode(payload, _jwt_secret(), algorithm=ALGORITHM)


def decode_access_token_claims(token: str) -> AccessTokenClaims:
    try:
        payload = jwt.decode(
            token,
            _jwt_secret(),
            algorithms=[ALGORITHM],
        )
    except jwt.PyJWTError as e:
        raise ValueError(str(e)) from e
    if payload.get("type") != "access":
        raise ValueError("wrong token type")
    sub = payload.get("sub")
    if not sub:
        raise ValueError("missing sub")
    raw_tv = payload.get("tv", 0)
    if isinstance(raw_tv, bool) or not isinstance(raw_tv, int) or raw_tv < 0:
        raise ValueError("invalid token version")
    return AccessTokenClaims(user_id=uuid.UUID(str(sub)), token_version=raw_tv)


def decode_access_token(token: str) -> uuid.UUID:
    return decode_access_token_claims(token).user_id
