import json
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path

from fastapi.routing import APIRoute
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


def _collect_route_ops() -> list[dict[str, str]]:
    operations: list[dict[str, str]] = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        for method in sorted(route.methods or []):
            if method in {"HEAD", "OPTIONS"}:
                continue
            operations.append({"method": method, "path": route.path})
    return sorted(operations, key=lambda item: (item["path"], item["method"]))


def _load_snapshot_ops() -> list[dict[str, str]]:
    snapshot_path = Path(__file__).parent / "fixtures" / "api_operations_snapshot.json"
    return json.loads(snapshot_path.read_text(encoding="utf-8"))


def test_api_operations_match_snapshot() -> None:
    assert _collect_route_ops() == _load_snapshot_ops()


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
