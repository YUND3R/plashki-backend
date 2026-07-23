from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.errors import (
    AppError,
    http_status_for_error,
    lobby_host_mutation_error,
)


async def application_error_handler(
    _request: Request,
    exc: AppError,
) -> JSONResponse:
    return JSONResponse(
        status_code=http_status_for_error(exc.code),
        content={"detail": exc.detail},
    )


def raise_lobby_host_mutation_error(err: str | None) -> None:
    application_error = lobby_host_mutation_error(err)
    if application_error is not None:
        raise application_error
