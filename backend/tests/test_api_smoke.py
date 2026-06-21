from contextlib import asynccontextmanager, contextmanager
from typing import AsyncGenerator

from fastapi.testclient import TestClient

from app.db.session import get_session
from app.main import app


@asynccontextmanager
async def _noop_lifespan(_app):
    yield


class _DummySession:
    async def execute(self, *_args, **_kwargs):
        return None


async def _override_get_session() -> AsyncGenerator[_DummySession, None]:
    yield _DummySession()


@contextmanager
def _make_client():
    app.router.lifespan_context = _noop_lifespan
    app.dependency_overrides[get_session] = _override_get_session
    client = TestClient(app)
    try:
        yield client
    finally:
        client.close()
        app.dependency_overrides.pop(get_session, None)


def test_root_endpoint_alive() -> None:
    with _make_client() as client:
        resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json() == {"message": "Plashki API"}


def test_health_endpoint_alive() -> None:
    with _make_client() as client:
        resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json().get("status") == "ok"


def test_openapi_contains_key_paths() -> None:
    with _make_client() as client:
        resp = client.get("/openapi.json")
    assert resp.status_code == 200
    paths = resp.json().get("paths", {})
    assert "/auth/login" in paths
    assert "/lobbies" in paths
    assert "/images/nanobanana/process" in paths


def test_protected_endpoint_requires_auth_cookie() -> None:
    with _make_client() as client:
        resp = client.get("/auth/me")
    assert resp.status_code == 401
    assert "Нужна авторизация" in resp.json().get("detail", "")
