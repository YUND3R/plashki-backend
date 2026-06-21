import uuid

import pytest
from fastapi import HTTPException
from starlette.requests import Request

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


def test_get_current_user_id_get_no_csrf_required(monkeypatch: pytest.MonkeyPatch) -> None:
    user_id = uuid.uuid4()
    monkeypatch.setattr(auth_deps, "decode_access_token", lambda _token: user_id)
    req = _make_request(
        method="GET",
        cookie_header="plashki_access_token=test-token",
    )
    assert auth_deps.get_current_user_id(req) == user_id


def test_get_current_user_id_patch_requires_csrf(monkeypatch: pytest.MonkeyPatch) -> None:
    user_id = uuid.uuid4()
    monkeypatch.setattr(auth_deps, "decode_access_token", lambda _token: user_id)
    req = _make_request(
        method="PATCH",
        cookie_header="plashki_access_token=test-token; plashki_csrf_token=abc",
        csrf_header=None,
    )
    with pytest.raises(HTTPException) as exc:
        auth_deps.get_current_user_id(req)
    assert exc.value.status_code == 403


def test_get_current_user_id_patch_rejects_mismatched_csrf(monkeypatch: pytest.MonkeyPatch) -> None:
    user_id = uuid.uuid4()
    monkeypatch.setattr(auth_deps, "decode_access_token", lambda _token: user_id)
    req = _make_request(
        method="PATCH",
        cookie_header="plashki_access_token=test-token; plashki_csrf_token=abc",
        csrf_header="wrong",
    )
    with pytest.raises(HTTPException) as exc:
        auth_deps.get_current_user_id(req)
    assert exc.value.status_code == 403


def test_get_current_user_id_patch_accepts_matching_csrf(monkeypatch: pytest.MonkeyPatch) -> None:
    user_id = uuid.uuid4()
    monkeypatch.setattr(auth_deps, "decode_access_token", lambda _token: user_id)
    req = _make_request(
        method="PATCH",
        cookie_header="plashki_access_token=test-token; plashki_csrf_token=abc",
        csrf_header="abc",
    )
    assert auth_deps.get_current_user_id(req) == user_id


def test_get_current_user_id_without_token_401() -> None:
    req = _make_request(method="GET")
    with pytest.raises(HTTPException) as exc:
        auth_deps.get_current_user_id(req)
    assert exc.value.status_code == 401
