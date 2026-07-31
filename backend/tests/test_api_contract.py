from contextlib import asynccontextmanager, contextmanager

from fastapi.testclient import TestClient

from app.db.session import get_session
from app.main import app


@asynccontextmanager
async def _noop_lifespan(_app):
    yield


class _DummySession:
    async def execute(self, *_args, **_kwargs):
        return None


async def _override_get_session():
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


def test_all_mutating_openapi_operations_have_csrf_header_param() -> None:
    with _make_client() as client:
        openapi = client.get("/openapi.json").json()

    csrf_header = "X-CSRF-Token"
    for path, path_item in openapi.get("paths", {}).items():
        for method, operation in path_item.items():
            if method.lower() not in {"post", "put", "patch", "delete"}:
                continue
            params = operation.get("parameters", [])
            has_csrf = any(
                isinstance(p, dict)
                and p.get("in") == "header"
                and p.get("name") == csrf_header
                for p in params
            )
            assert has_csrf, f"Missing {csrf_header} for {method.upper()} {path}"


def test_openapi_has_critical_endpoints() -> None:
    with _make_client() as client:
        openapi = client.get("/openapi.json").json()

    paths = openapi.get("paths", {})
    required_ops = {
        ("POST", "/auth/login"),
        ("GET", "/auth/me"),
        ("POST", "/users/{owner_user_id}/player-cards"),
        ("POST", "/users/{owner_user_id}/player-cards/{card_id}/photo"),
        ("POST", "/images/nanobanana/process"),
        ("POST", "/lobbies"),
        ("GET", "/lobbies/{lobby_id}/overlay-state"),
        ("GET", "/ratings/{rating_id}/games"),
        ("GET", "/ratings/{rating_id}/games/{game_id}"),
    }
    missing: list[str] = []
    for method, path in required_ops:
        method_obj = paths.get(path, {}).get(method.lower())
        if not isinstance(method_obj, dict):
            missing.append(f"{method} {path}")
    assert not missing, f"Missing critical OpenAPI operations: {', '.join(sorted(missing))}"


def test_openapi_operation_ids_are_unique() -> None:
    with _make_client() as client:
        openapi = client.get("/openapi.json").json()

    operation_ids: list[str] = []
    for path_item in openapi.get("paths", {}).values():
        if not isinstance(path_item, dict):
            continue
        for operation in path_item.values():
            if isinstance(operation, dict) and isinstance(operation.get("operationId"), str):
                operation_ids.append(operation["operationId"])

    assert len(operation_ids) == len(set(operation_ids)), "Duplicate OpenAPI operationId found."
