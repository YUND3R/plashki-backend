from dataclasses import dataclass
from enum import StrEnum


class ErrorCode(StrEnum):
    LOBBY_NOT_FOUND = "lobby_not_found"
    LOBBY_HOST_REQUIRED = "lobby_host_required"
    LOBBY_MEMBERSHIP_NOT_FOUND = "lobby_membership_not_found"


_HTTP_STATUS_BY_CODE: dict[ErrorCode, int] = {
    ErrorCode.LOBBY_NOT_FOUND: 404,
    ErrorCode.LOBBY_HOST_REQUIRED: 403,
    ErrorCode.LOBBY_MEMBERSHIP_NOT_FOUND: 404,
}


@dataclass(slots=True)
class AppError(Exception):
    """Transport-independent base for typed domain/application failures."""

    code: ErrorCode
    detail: str

    def __post_init__(self) -> None:
        Exception.__init__(self, self.detail)


class DomainError(AppError):
    """A business-rule failure raised by the domain layer."""


class ApplicationError(AppError):
    """A use-case failure raised by the application layer."""


def http_status_for_error(code: ErrorCode) -> int:
    return _HTTP_STATUS_BY_CODE[code]


def lobby_host_mutation_error(error: str | None) -> ApplicationError | None:
    """Translate legacy lobby result codes without changing their API contract."""

    if error == "lobby_not_found":
        return ApplicationError(ErrorCode.LOBBY_NOT_FOUND, "Лобби не найдено")
    if error == "not_host":
        return ApplicationError(
            ErrorCode.LOBBY_HOST_REQUIRED,
            "Менять роли и статусы может только хост лобби.",
        )
    if error == "membership_not_found":
        return ApplicationError(
            ErrorCode.LOBBY_MEMBERSHIP_NOT_FOUND,
            "Место не найдено в этом лобби.",
        )
    return None
