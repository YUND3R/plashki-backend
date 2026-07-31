from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from starlette.staticfiles import StaticFiles

from app.broadcast.api.router import router as broadcast_router
from app.core.config import settings
from app.core.errors import AppError
from app.db.session import engine
from app.identity.api.router_admin import router as admin_router
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.routers import auth as auth_routes
from app.routers import dev as dev_routes
from app.routers import feedback as feedback_routes
from app.routers import nanobanana as nanobanana_routes
from app.routers import player_card as player_card_routes
from app.routers import shop as shop_routes
from app.ratings.api.router import router as ratings_router
from app.sessions.api.router import router as sessions_router
from app.shared.api.errors import application_error_handler
from app.shared.api.router_system import router as system_router


def _upload_dir() -> Path:
    upload_dir = Path(settings.upload_dir)
    if not upload_dir.is_absolute():
        upload_dir = Path.cwd() / upload_dir
    return upload_dir


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    _upload_dir().mkdir(parents=True, exist_ok=True)
    yield
    await engine.dispose()


def _customize_openapi(app: FastAPI) -> None:
    csrf_safe_methods = frozenset({"get", "head", "options", "trace"})

    def openapi_with_csrf_header() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title,
            version=app.version,
            openapi_version=app.openapi_version,
            description=app.description,
            routes=app.routes,
        )
        param = {
            "name": settings.csrf_header_name,
            "in": "header",
            "required": False,
            "schema": {"type": "string"},
        }
        for path_item in schema.get("paths", {}).values():
            if not isinstance(path_item, dict):
                continue
            for method, operation in path_item.items():
                if method in csrf_safe_methods or not isinstance(operation, dict):
                    continue
                params = operation.setdefault("parameters", [])
                if not any(
                    item.get("name") == settings.csrf_header_name
                    and item.get("in") == "header"
                    for item in params
                    if isinstance(item, dict)
                ):
                    params.append(param)
        app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = openapi_with_csrf_header  # type: ignore[method-assign]


def create_app() -> FastAPI:
    openapi_url = "/openapi.json" if settings.expose_openapi else None
    docs_url = "/docs" if settings.expose_openapi else None
    redoc_url = "/redoc" if settings.expose_openapi else None
    app = FastAPI(
        title="Plashki API",
        version="0.1.0",
        docs_url=docs_url,
        redoc_url=redoc_url,
        openapi_url=openapi_url,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_exception_handler(AppError, application_error_handler)

    if settings.dev_endpoints_enabled:
        app.include_router(dev_routes.router)
    for router in (
        auth_routes.router,
        feedback_routes.router,
        player_card_routes.router,
        shop_routes.router,
        nanobanana_routes.router,
        system_router,
        admin_router,
        sessions_router,
        broadcast_router,
        ratings_router,
    ):
        app.include_router(router)

    upload_dir = _upload_dir()
    upload_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/files", StaticFiles(directory=str(upload_dir)), name="files")
    if settings.expose_openapi:
        _customize_openapi(app)
    return app


app = create_app()
