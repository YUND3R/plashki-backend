from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class GomafiaSeat:
    seat_no: int
    nickname: str


@dataclass(frozen=True)
class GomafiaTable:
    tour_no: int
    table_no: int | None
    table_label: str
    seats: list[GomafiaSeat]


@dataclass(frozen=True)
class GomafiaTournament:
    source_url: str
    title: str
    tables: list[GomafiaTable]


class GomafiaTournamentSource(Protocol):
    def validate_url(self, url: str) -> str: ...

    def load(self, url: str) -> GomafiaTournament: ...


class InvalidGomafiaUrl(ValueError):
    pass


class GomafiaFetchError(RuntimeError):
    pass
