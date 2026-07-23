from urllib import error

from bs4 import BeautifulSoup

from app.services.gomafia_import import (
    _extract_tournament_title,
    _fetch_html,
    _parse_tours_from_html,
    _validate_gomafia_url,
)
from app.sessions.ports.gomafia import (
    GomafiaFetchError,
    GomafiaSeat,
    GomafiaTable,
    GomafiaTournament,
    InvalidGomafiaUrl,
)


def parse_gomafia_html(source_url: str, html: str) -> GomafiaTournament:
    soup = BeautifulSoup(html, "html.parser")
    return GomafiaTournament(
        source_url=source_url,
        title=_extract_tournament_title(soup),
        tables=[
            GomafiaTable(
                tour_no=table.tour_no,
                table_no=table.table_no,
                table_label=table.table_label,
                seats=[
                    GomafiaSeat(seat_no=seat.seat_no, nickname=seat.nickname)
                    for seat in table.seats
                ],
            )
            for table in _parse_tours_from_html(html)
        ],
    )


class GomafiaHttpParserAdapter:
    def validate_url(self, url: str) -> str:
        valid_url = _validate_gomafia_url(url)
        if valid_url is None:
            raise InvalidGomafiaUrl
        return valid_url

    def load(self, url: str) -> GomafiaTournament:
        valid_url = self.validate_url(url)
        try:
            html = _fetch_html(valid_url)
        except (TimeoutError, error.URLError, OSError) as exc:
            raise GomafiaFetchError from exc
        return parse_gomafia_html(valid_url, html)
