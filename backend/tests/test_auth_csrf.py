import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.core.security import AccessTokenClaims, create_access_token, decode_access_token_claims
from app.deps import auth as auth_deps


def _make_request(*, method: str, cookie_header: str = "", csrf_header: str | None = None) -> Request:
    headers: list[tuple[bytes, bytes]] = []
    if cookie_header:
        headers.append((b"cookie", cookie_header.encode("utf-8")))
    if csrf_header is not None:
        headers.append((b"x-csrf-token", csrf_header.encode("utf-8")))
    scope = {
        "type": "http",
        "method": method,
        "path": "/",
        "headers": headers,
    }
    return Request(scope)


def _session_for_user(*, user_id: uuid.UUID, token_version: int) -> AsyncMock:
    user = MagicMock()
    user.token_version = token_version
    session = AsyncMock()
    session.get = AsyncMock(return_value=user)
    return session


def test_get_current_user_id_get_no_csrf_required(monkeypatch: pytest.MonkeyPatch) -> None:
    user_id = uuid.uuid4()
    claims = AccessTokenClaims(user_id=user_id, token_version=0)
    monkeypatch.setattr(auth_deps, "decode_access_token_claims", lambda _token: claims)
    req = _make_request(
        method="GET",
        cookie_header="plashki_access_token=test-token",
    )
    session = _session_for_user(user_id=user_id, token_version=0)
    assert asyncio.run(auth_deps.get_current_user_id(req, session=session)) == user_id


def test_get_current_user_id_patch_requires_csrf(monkeypatch: pytest.MonkeyPatch) -> None:
    user_id = uuid.uuid4()
    claims = AccessTokenClaims(user_id=user_id, token_version=0)
    monkeypatch.setattr(auth_deps, "decode_access_token_claims", lambda _token: claims)
    req = _make_request(
        method="PATCH",
        cookie_header="plashki_access_token=test-token; plashki_csrf_token=abc",
        csrf_header=None,
    )
    session = _session_for_user(user_id=user_id, token_version=0)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(auth_deps.get_current_user_id(req, session=session))
    assert exc.value.status_code == 403


def test_get_current_user_id_patch_rejects_mismatched_csrf(monkeypatch: pytest.MonkeyPatch) -> None:
    user_id = uuid.uuid4()
    claims = AccessTokenClaims(user_id=user_id, token_version=0)
    monkeypatch.setattr(auth_deps, "decode_access_token_claims", lambda _token: claims)
    req = _make_request(
        method="PATCH",
        cookie_header="plashki_access_token=test-token; plashki_csrf_token=abc",
        csrf_header="wrong",
    )
    session = _session_for_user(user_id=user_id, token_version=0)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(auth_deps.get_current_user_id(req, session=session))
    assert exc.value.status_code == 403


def test_get_current_user_id_patch_accepts_matching_csrf(monkeypatch: pytest.MonkeyPatch) -> None:
    user_id = uuid.uuid4()
    claims = AccessTokenClaims(user_id=user_id, token_version=0)
    monkeypatch.setattr(auth_deps, "decode_access_token_claims", lambda _token: claims)
    req = _make_request(
        method="PATCH",
        cookie_header="plashki_access_token=test-token; plashki_csrf_token=abc",
        csrf_header="abc",
    )
    session = _session_for_user(user_id=user_id, token_version=0)
    assert asyncio.run(auth_deps.get_current_user_id(req, session=session)) == user_id


def test_get_current_user_id_without_token_401() -> None:
    req = _make_request(method="GET")
    session = AsyncMock()
    with pytest.raises(HTTPException) as exc:
        asyncio.run(auth_deps.get_current_user_id(req, session=session))
    assert exc.value.status_code == 401


def test_get_current_user_id_rejects_stale_token_version(monkeypatch: pytest.MonkeyPatch) -> None:
    user_id = uuid.uuid4()
    claims = AccessTokenClaims(user_id=user_id, token_version=0)
    monkeypatch.setattr(auth_deps, "decode_access_token_claims", lambda _token: claims)
    req = _make_request(
        method="GET",
        cookie_header="plashki_access_token=test-token",
    )
    session = _session_for_user(user_id=user_id, token_version=1)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(auth_deps.get_current_user_id(req, session=session))
    assert exc.value.status_code == 401
    assert "Сессия недействительна" in exc.value.detail


def test_access_token_roundtrip_includes_token_version() -> None:
    user_id = uuid.uuid4()
    token = create_access_token(user_id=user_id, token_version=3)
    claims = decode_access_token_claims(token)
    assert claims.user_id == user_id
    assert claims.token_version == 3
