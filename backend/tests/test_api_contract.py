from contextlib import asynccontextmanager, contextmanager

import re
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


def test_openapi_and_registered_routes_are_consistent() -> None:
    with _make_client() as client:
        openapi = client.get("/openapi.json").json()

    openapi_ops: set[tuple[str, str]] = set()
    for path, path_item in openapi.get("paths", {}).items():
        for method in path_item.keys():
            openapi_ops.add((method.upper(), path))

    route_ops: set[tuple[str, str]] = set()
    param_pattern = re.compile(r"\{([^}:]+):[^}]+\}")
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if not route.include_in_schema:
            continue
        normalized_path = param_pattern.sub(r"{\1}", route.path)
        for method in route.methods or set():
            if method in {"HEAD", "OPTIONS"}:
                continue
            route_ops.add((method, normalized_path))

    # OpenAPI не должен терять зарегистрированные ручки и не должен содержать «битых» операций.
    assert route_ops == openapi_ops
