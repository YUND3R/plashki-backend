"""Ссылки подтверждения email: фронт — hash-фрагмент (секрет не попадает в access-log при первом GET)."""

import uuid
from urllib.parse import quote

from starlette.requests import Request

from app.core.config import settings


def build_email_verification_link(
    *,
    token_id: uuid.UUID,
    signature: str,
    request: Request | None = None,
) -> str:
    fe = settings.frontend_verify_email_url.strip()
    if fe:
        base = fe.split("#")[0].rstrip("/")
        return f"{base}#vid={token_id}&sig={quote(signature, safe='')}"

    pub = settings.public_base_url.strip().rstrip("/")
    if pub:
        return f"{pub}/auth/verify-email/{token_id}/{signature}"

    if request is not None:
        b = str(request.base_url).rstrip("/")
        return f"{b}/auth/verify-email/{token_id}/{signature}"

    return f"/auth/verify-email/{token_id}/{signature}"
