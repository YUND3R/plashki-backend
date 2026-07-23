import asyncio
import json

import pytest

from app.core.errors import ErrorCode, lobby_host_mutation_error
from app.main import application_error_handler


@pytest.mark.parametrize(
    ("legacy_code", "expected_code", "expected_status", "expected_detail"),
    [
        ("lobby_not_found", ErrorCode.LOBBY_NOT_FOUND, 404, "Лобби не найдено"),
        (
            "not_host",
            ErrorCode.LOBBY_HOST_REQUIRED,
            403,
            "Менять роли и статусы может только хост лобби.",
        ),
        (
            "membership_not_found",
            ErrorCode.LOBBY_MEMBERSHIP_NOT_FOUND,
            404,
            "Место не найдено в этом лобби.",
        ),
    ],
)
def test_lobby_error_mapper_preserves_http_contract(
    legacy_code: str,
    expected_code: ErrorCode,
    expected_status: int,
    expected_detail: str,
) -> None:
    error = lobby_host_mutation_error(legacy_code)
    assert error is not None
    assert error.code is expected_code

    response = asyncio.run(
        application_error_handler(None, error)  # type: ignore[arg-type]
    )

    assert response.status_code == expected_status
    assert json.loads(response.body) == {"detail": expected_detail}
