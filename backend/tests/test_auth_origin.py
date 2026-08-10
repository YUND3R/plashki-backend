import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.deps import origin as origin_deps


def _request(*, headers: dict[str, str]) -> Request:
    return Request(
        {
            "type": "http",
            "scheme": "https",
            "method": "POST",
            "path": "/auth/reset-password-form",
            "headers": [(key.lower().encode(), value.encode()) for key, value in headers.items()],
            "server": ("api.plash-ki.ru", 443),
        }
    )


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        environment="development",
        cors_origin_list=["https://plash-ki.ru"],
    )


def test_origin_allows_same_api_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(origin_deps, "settings", _settings())
    request = _request(headers={"origin": "https://api.plash-ki.ru"})
    asyncio.run(origin_deps.require_trusted_origin(request))


def test_origin_rejects_cross_site_browser_post(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(origin_deps, "settings", _settings())
    request = _request(headers={"origin": "https://evil.example"})
    with pytest.raises(HTTPException) as exc:
        asyncio.run(origin_deps.require_trusted_origin(request))
    assert exc.value.status_code == 403


def test_origin_allows_non_browser_client_without_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(origin_deps, "settings", _settings())
    asyncio.run(origin_deps.require_trusted_origin(_request(headers={})))
