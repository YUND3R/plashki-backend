from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
import uuid

from fastapi.testclient import TestClient

from app.db.models import GameLobby, UserProfile
from app.db.session import get_session
from app.deps.auth import get_current_user_id
from app.main import app
from app.db.base import OverlayDesign


@asynccontextmanager
async def _noop_lifespan(_app):
    yield


class _FakeSession:
    def __init__(self, user: SimpleNamespace | None, lobbies: dict[uuid.UUID, SimpleNamespace]):
        self._user = user
        self._lobbies = lobbies
        self.commit_calls = 0

    async def get(self, model, ident):
        if model is UserProfile:
            if self._user is not None and self._user.id == ident:
                return self._user
            return None
        if model is GameLobby:
            return self._lobbies.get(ident)
        return None

    async def commit(self):
        self.commit_calls += 1
        if self._user is not None:
            self._user.updated_at = datetime.now(timezone.utc)

    async def refresh(self, _obj):
        return None


@contextmanager
def _make_client(session: _FakeSession, current_user_id: uuid.UUID):
    async def _override_get_session():
        yield session

    async def _override_get_current_user_id():
        return current_user_id

    app.router.lifespan_context = _noop_lifespan
    app.dependency_overrides[get_session] = _override_get_session
    app.dependency_overrides[get_current_user_id] = _override_get_current_user_id
    client = TestClient(app)
    try:
        yield client
    finally:
        client.close()
        app.dependency_overrides.pop(get_session, None)
        app.dependency_overrides.pop(get_current_user_id, None)


def test_host_can_switch_active_lobby() -> None:
    user_id = uuid.uuid4()
    lobby_id = uuid.uuid4()
    user = SimpleNamespace(id=user_id, active_overlay_lobby_id=None, updated_at=datetime.now(timezone.utc))
    lobby = SimpleNamespace(id=lobby_id, host_user_id=user_id, active_overlay_screen="lobby", selected_overlay_design=OverlayDesign.CLASSIC)
    session = _FakeSession(user=user, lobbies={lobby_id: lobby})

    with _make_client(session, user_id) as client:
        resp = client.patch("/overlay/active-lobby", json={"lobby_id": str(lobby_id)})

    assert resp.status_code == 200
    assert resp.json()["active_lobby_id"] == str(lobby_id)


def test_non_host_gets_403_on_switch_active_lobby() -> None:
    host_id = uuid.uuid4()
    user_id = uuid.uuid4()
    lobby_id = uuid.uuid4()
    user = SimpleNamespace(id=user_id, active_overlay_lobby_id=None, updated_at=datetime.now(timezone.utc))
    lobby = SimpleNamespace(id=lobby_id, host_user_id=host_id, active_overlay_screen="lobby", selected_overlay_design=OverlayDesign.CLASSIC)
    session = _FakeSession(user=user, lobbies={lobby_id: lobby})

    with _make_client(session, user_id) as client:
        resp = client.patch("/overlay/active-lobby", json={"lobby_id": str(lobby_id)})

    assert resp.status_code == 403


def test_invalid_lobby_uuid_returns_400() -> None:
    user_id = uuid.uuid4()
    user = SimpleNamespace(id=user_id, active_overlay_lobby_id=None, updated_at=datetime.now(timezone.utc))
    session = _FakeSession(user=user, lobbies={})

    with _make_client(session, user_id) as client:
        resp = client.patch("/overlay/active-lobby", json={"lobby_id": "not-a-uuid"})

    assert resp.status_code == 400


def test_overlay_state_reflects_new_active_lobby_after_patch() -> None:
    user_id = uuid.uuid4()
    lobby_id = uuid.uuid4()
    user = SimpleNamespace(id=user_id, active_overlay_lobby_id=None, updated_at=datetime.now(timezone.utc))
    lobby = SimpleNamespace(
        id=lobby_id,
        host_user_id=user_id,
        active_overlay_screen="roles",
        selected_overlay_design=OverlayDesign.PLUS,
        show_victory_scores=False,
    )
    session = _FakeSession(user=user, lobbies={lobby_id: lobby})

    with _make_client(session, user_id) as client:
        patch_resp = client.patch("/overlay/active-lobby", json={"lobby_id": str(lobby_id)})
        state_resp = client.get("/overlay/state")

    assert patch_resp.status_code == 200
    assert state_resp.status_code == 200
    payload = state_resp.json()
    assert payload["active_lobby_id"] == str(lobby_id)
    assert payload["active_overlay_screen"] == "roles"
    assert payload["selected_overlay_design"] == "plus"
    assert payload["show_victory_scores"] is False


def test_overlay_state_auto_resets_when_active_lobby_missing() -> None:
    user_id = uuid.uuid4()
    missing_lobby_id = uuid.uuid4()
    user = SimpleNamespace(
        id=user_id,
        active_overlay_lobby_id=missing_lobby_id,
        updated_at=datetime.now(timezone.utc),
    )
    session = _FakeSession(user=user, lobbies={})

    with _make_client(session, user_id) as client:
        resp = client.get("/overlay/state")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["active_lobby_id"] is None
    assert payload["active_overlay_screen"] == "lobby"
    assert payload["selected_overlay_design"] == "classic"
    assert user.active_overlay_lobby_id is None
    assert session.commit_calls >= 1
