import uuid
from urllib.parse import quote

from starlette.requests import Request

from app.core.config import settings


def build_password_reset_link(
    *,
    token_id: uuid.UUID,
    signature: str,
    request: Request | None = None,
) -> str:
    fe = settings.frontend_reset_password_url.strip()
    if fe:
        base = fe.split("#")[0].rstrip("/")
        return f"{base}#rid={token_id}&sig={quote(signature, safe='')}"

    pub = settings.public_base_url.strip().rstrip("/")
    if pub:
        return (
            f"{pub}/auth/reset-password-form?rid={token_id}&sig={quote(signature, safe='')}"
        )

    if request is not None:
        b = str(request.base_url).rstrip("/")
        return (
            f"{b}/auth/reset-password-form?rid={token_id}&sig={quote(signature, safe='')}"
        )

    return f"/auth/reset-password-form?rid={token_id}&sig={quote(signature, safe='')}"
