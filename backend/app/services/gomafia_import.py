import re
import uuid
from dataclasses import dataclass
from urllib import error, parse, request

from bs4 import BeautifulSoup, NavigableString
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import GameLobby, LobbyMembership, PlayerCard, UserProfile
from app.schemas.lobby import ImportedLobbyInfo, ImportGomafiaTournamentResponse


@dataclass(frozen=True)
class ParsedSeat:
    seat_no: int
    nickname: str


@dataclass(frozen=True)
class ParsedTourTable:
    tour_no: int
    table_no: int | None
    table_label: str
    seats: list[ParsedSeat]


def _decode_html_bytes(raw: bytes, content_type: str | None) -> str:
    candidates: list[str] = []
    if content_type:
        match = re.search(r"charset=([A-Za-z0-9._-]+)", content_type, flags=re.IGNORECASE)
        if match is not None:
            candidates.append(match.group(1).strip().lower())
    candidates.extend(["utf-8", "cp1251", "windows-1251", "koi8-r"])

    best_text = raw.decode("utf-8", errors="replace")
    best_score = (-1, -best_text.count("\ufffd"))
    seen: set[str] = set()
    for enc in candidates:
        if not enc or enc in seen:
            continue
        seen.add(enc)
        try:
            text = raw.decode(enc, errors="replace")
        except LookupError:
            continue
        # Чем больше маркеров турнира и чем меньше замен, тем лучше.
        marker_hits = (
            len(re.findall(r"\bТур\b", text, flags=re.IGNORECASE))
            + len(re.findall(r"\bСтол\b", text, flags=re.IGNORECASE))
            + len(re.findall(r"\bПобеда\b", text, flags=re.IGNORECASE))
        )
        score = (marker_hits, -text.count("\ufffd"))
        if score > best_score:
            best_score = score
            best_text = text
    return best_text


def _validate_gomafia_url(raw_url: str) -> str | None:
    url = raw_url.strip()
    if not url:
        return None
    try:
        parsed = parse.urlparse(url)
    except ValueError:
        return None
    host = (parsed.netloc or "").lower()
    if parsed.scheme not in ("http", "https"):
        return None
    if host not in ("gomafia.pro", "www.gomafia.pro"):
        return None
    if not parsed.path.startswith("/tournament/"):
        return None
    return url


def _fetch_html(url: str) -> str:
    req = request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; PlashkiBot/1.0)",
            "Accept": "text/html,application/xhtml+xml",
        },
        method="GET",
    )
    with request.urlopen(req, timeout=20) as resp:
        raw = resp.read()
        return _decode_html_bytes(raw, resp.headers.get("Content-Type"))


def _extract_tournament_title(soup: BeautifulSoup) -> str:
    plain = soup.get_text("\n", strip=True)
    match = re.search(r"\n([^\n]{3,120})\nДаты проведения турнира", plain)
    if match is not None:
        return match.group(1).strip()[:120]
    for h in soup.find_all(["h1", "h2", "h3"]):
        text = h.get_text(" ", strip=True)
        if text and not re.search(r"Тур\s*\d+", text):
            return text[:120]
    return "Импорт Gomafia"


def _extract_table_label(table) -> str:
    first_row = table.find("tr")
    if first_row is None:
        return "Стол"
    cells = [cell.get_text(" ", strip=True) for cell in first_row.find_all(["td", "th"])]
    if len(cells) >= 2 and cells[1].strip():
        return cells[1].strip()
    return "Стол"


def _extract_nearest_tour_no(table) -> int | None:
    # Сначала пытаемся найти номер тура максимально рядом с таблицей.
    for sibling in table.find_previous_siblings(limit=12):
        raw = sibling.get_text(" ", strip=True)
        if not raw:
            continue
        match = re.search(r"\bТур\s*(\d+)\b", raw, flags=re.IGNORECASE)
        if match is not None:
            return int(match.group(1))

    header = table.find_previous(["h1", "h2", "h3", "h4", "h5", "h6"])
    if header is not None:
        raw_header = header.get_text(" ", strip=True)
        match = re.search(r"\bТур\s*(\d+)\b", raw_header, flags=re.IGNORECASE)
        if match is not None:
            return int(match.group(1))

    for text in table.find_all_previous(string=True, limit=120):
        raw = str(text).strip()
        if not raw:
            continue
        match = re.search(r"\bТур\s*(\d+)\b", raw, flags=re.IGNORECASE)
        if match is not None:
            return int(match.group(1))
    return None


def _extract_table_no_from_label(table_label: str) -> int | None:
    match = re.search(r"\bСтол\s*(\d+)\b", table_label, flags=re.IGNORECASE)
    if match is not None:
        return int(match.group(1))
    plain = table_label.strip()
    if plain.isdigit():
        return int(plain)
    return None


def _extract_tour_no_from_text(raw: str) -> int | None:
    match = re.search(r"\b(?:Тур|Tur|Tour)\s*(\d+)\b", raw, flags=re.IGNORECASE)
    if match is None:
        return None
    return int(match.group(1))


def _parse_tours_from_html(html: str) -> list[ParsedTourTable]:
    soup = BeautifulSoup(html, "html.parser")
    parsed_tables: list[ParsedTourTable] = []
    auto_tour_no = 1
    current_tour_no: int | None = None
    inferred_tour_no = 1
    inferred_last_table_no: int | None = None

    # Идем по документу сверху вниз: как только встретили "Тур N", все следующие
    # таблицы относятся к этому туру до появления нового "Тур M".
    for node in soup.descendants:
        if isinstance(node, NavigableString):
            raw = str(node).strip()
            if not raw:
                continue
            detected_tour = _extract_tour_no_from_text(raw)
            if detected_tour is not None:
                current_tour_no = detected_tour
            continue
        if getattr(node, "name", None) != "table":
            continue
        table = node
        rows = table.find_all("tr")
        seats: list[ParsedSeat] = []
        used_seats: set[int] = set()

        for row in rows:
            cells = [cell.get_text(" ", strip=True) for cell in row.find_all(["td", "th"])]
            if len(cells) < 2:
                continue
            seat_raw = cells[0].strip()
            if not seat_raw.isdigit():
                continue
            seat_no = int(seat_raw)
            if seat_no < 1 or seat_no > 20 or seat_no in used_seats:
                continue
            nickname = cells[1].strip()
            if not nickname:
                continue
            used_seats.add(seat_no)
            seats.append(ParsedSeat(seat_no=seat_no, nickname=nickname))

        # Отсекаем нерелевантные таблицы: у игровых туров обычно >=5 мест.
        if len(seats) < 5:
            continue
        seats.sort(key=lambda s: s.seat_no)
        parsed_table_no = _extract_table_no_from_label(_extract_table_label(table))
        tour_no = current_tour_no
        if tour_no is None:
            tour_no = _extract_nearest_tour_no(table)
        if tour_no is None:
            # fallback для вёрстки вида:
            # Тур 1: Стол 1..N, Тур 2: Стол 1..N
            if parsed_table_no is not None:
                if (
                    inferred_last_table_no is not None
                    and parsed_table_no <= inferred_last_table_no
                ):
                    inferred_tour_no += 1
                inferred_last_table_no = parsed_table_no
                tour_no = inferred_tour_no
            else:
                tour_no = auto_tour_no
                auto_tour_no += 1
        parsed_tables.append(
            ParsedTourTable(
                tour_no=tour_no,
                table_no=parsed_table_no,
                table_label=_extract_table_label(table),
                seats=seats,
            )
        )

    return parsed_tables


async def _get_or_create_player_card_for_nickname(
    session: AsyncSession,
    owner_user_id: uuid.UUID,
    nickname: str,
) -> PlayerCard:
    result = await session.execute(
        select(PlayerCard)
        .where(
            PlayerCard.owner_user_id == owner_user_id,
            PlayerCard.nickname == nickname,
        )
        .limit(1)
    )
    card = result.scalars().first()
    if card is not None:
        return card

    card = PlayerCard(
        owner_user_id=owner_user_id,
        first_name=nickname[:100],
        last_name="",
        nickname=nickname[:255],
        club=None,
        gomafia_url=None,
        photo_urls=[],
    )
    session.add(card)
    await session.flush()
    return card


async def import_gomafia_tournament_to_lobbies(
    session: AsyncSession,
    *,
    acting_user_id: uuid.UUID,
    url: str,
) -> tuple[str | None, ImportGomafiaTournamentResponse | None]:
    valid_url = _validate_gomafia_url(url)
    if valid_url is None:
        return "invalid_url", None

    host = await session.get(UserProfile, acting_user_id)
    if host is None:
        return "host_not_found", None

    try:
        html = _fetch_html(valid_url)
    except (TimeoutError, error.URLError, OSError):
        return "fetch_failed", None

    soup = BeautifulSoup(html, "html.parser")
    tournament_title = _extract_tournament_title(soup)
    parsed_tables = _parse_tours_from_html(html)
    if not parsed_tables:
        return "parse_failed", None

    nickname_cache: dict[str, PlayerCard] = {}
    per_tour_counts: dict[int, int] = {}
    for item in parsed_tables:
        per_tour_counts[item.tour_no] = per_tour_counts.get(item.tour_no, 0) + 1

    raw_variants: list[dict] = []
    seen_tables_by_tour: dict[int, int] = {}
    max_players = 10
    for parsed in parsed_tables:
        tour_no = parsed.tour_no
        seats = parsed.seats
        table_label = parsed.table_label
        has_multiple_tables_in_tour = per_tour_counts.get(tour_no, 0) > 1
        table_index_in_tour = seen_tables_by_tour.get(tour_no, 0) + 1
        seen_tables_by_tour[tour_no] = table_index_in_tour
        parsed_table_no = parsed.table_no
        table_no = parsed_table_no if parsed_table_no is not None else table_index_in_tour

        variant_title = f"Тур {tour_no}"
        if has_multiple_tables_in_tour:
            variant_title = f"{variant_title} — Стол {table_no}"
        max_players = max(max_players, max(seat.seat_no for seat in seats), 10)

        variant_seats: list[dict] = []
        for seat in seats:
            card = nickname_cache.get(seat.nickname)
            if card is None:
                card = await _get_or_create_player_card_for_nickname(
                    session, acting_user_id, seat.nickname
                )
                nickname_cache[seat.nickname] = card

            variant_seats.append(
                {
                    "seat_no": seat.seat_no,
                    "seat_order": seat.seat_no - 1,
                    "nickname": seat.nickname,
                    "player_card_id": str(card.id),
                }
            )

        raw_variants.append(
            {
                "key": f"tour-{tour_no}-table-{table_no}",
                "title": variant_title[:120],
                "tour_no": tour_no,
                "table_label": f"Стол {table_no}",
                "players_count": len(seats),
                "seats": variant_seats,
            }
        )

    if not raw_variants:
        return "parse_failed", None

    first_variant = raw_variants[0]
    lobby = GameLobby(
        max_players=max_players,
        title=tournament_title[:120],
        host_user_id=acting_user_id,
        imported_source_url=valid_url,
        imported_current_key=str(first_variant["key"]),
        imported_variants=raw_variants,
    )
    session.add(lobby)
    await session.flush()

    for raw_seat in first_variant["seats"]:
        session.add(
            LobbyMembership(
                lobby_id=lobby.id,
                player_card_id=uuid.UUID(str(raw_seat["player_card_id"])),
                seat_order=int(raw_seat["seat_order"]),
            )
        )

    await session.commit()
    created_lobbies = [
        ImportedLobbyInfo(
            lobby_id=lobby.id,
            title=lobby.title,
            players_count=int(first_variant["players_count"]),
        )
    ]
    return (
        None,
        ImportGomafiaTournamentResponse(
            source_url=valid_url,
            created_lobbies=created_lobbies,
        ),
    )
