import asyncio
import uuid
from datetime import date, datetime
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.db.base import GameRole, RatingGameSource, RatingWinnerSide
from app.db.models import RatingGameResult
from app.ratings.application import ratings as ratings_app
from app.schemas.rating import (
    RatingGameBestMovePatch,
    RatingPatch,
    RatingSyncLobbyBody,
    RatingWrite,
)


def _game_result(
    *,
    player_card_id: uuid.UUID,
    role: GameRole,
    sort_order: int,
    bonus_points: float = 0.0,
    total_points: float = 0.0,
    best_move: list[str] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        player_card_id=player_card_id,
        role=role,
        bonus_points=bonus_points,
        total_points=total_points,
        best_move=best_move or ["", "", ""],
        sort_order=sort_order,
    )


def _game_with_seats(
    player_id: uuid.UUID,
    *,
    player_seat: int,
    player_role: GameRole,
    winner_side: RatingWinnerSide,
    best_move: list[str],
    bonus_points: float = 0.0,
    total_points: float = 0.0,
    seat_roles: dict[int, GameRole],
) -> SimpleNamespace:
    roles = dict(seat_roles)
    roles[player_seat] = player_role
    results = []
    for seat_num in sorted(roles):
        is_player = seat_num == player_seat
        results.append(
            _game_result(
                player_card_id=player_id if is_player else uuid.uuid4(),
                role=roles[seat_num],
                sort_order=seat_num - 1,
                bonus_points=bonus_points if is_player else 0.0,
                total_points=total_points if is_player else 0.0,
                best_move=best_move if is_player else ["", "", ""],
            )
        )
    return SimpleNamespace(winner_side=winner_side, results=results)


_STANDARD_SEAT_ROLES = {
    1: GameRole.MAFIA,
    2: GameRole.PEACEFUL,
    3: GameRole.DON,
    4: GameRole.PEACEFUL,
    5: GameRole.MAFIA,
}


def test_count_correct_mafia_hits() -> None:
    results = [
        _game_result(player_card_id=uuid.uuid4(), role=GameRole.MAFIA, sort_order=0),
        _game_result(player_card_id=uuid.uuid4(), role=GameRole.PEACEFUL, sort_order=1),
        _game_result(player_card_id=uuid.uuid4(), role=GameRole.DON, sort_order=2),
    ]
    assert ratings_app.count_correct_mafia_hits(["1", "2", "3"], results) == 2
    assert ratings_app.count_correct_mafia_hits(["1", "3", ""], results) == 2
    assert ratings_app.count_correct_mafia_hits(["2", "", ""], results) == 0
    assert ratings_app.count_correct_mafia_hits(["", "", ""], results) == 0


def test_count_correct_mafia_hits_ignores_duplicates_and_invalid() -> None:
    results = [
        _game_result(player_card_id=uuid.uuid4(), role=GameRole.MAFIA, sort_order=0),
        _game_result(player_card_id=uuid.uuid4(), role=GameRole.PEACEFUL, sort_order=1),
        _game_result(player_card_id=uuid.uuid4(), role=GameRole.DON, sort_order=2),
    ]
    # "1" duplicated should count once, non-numeric token should be ignored.
    assert ratings_app.count_correct_mafia_hits(["1", "1", "abc"], results) == 1


def test_rating_write_rejects_duplicate_player_cards() -> None:
    card_id = uuid.uuid4()
    with pytest.raises(ValidationError):
        RatingWrite(
            name="Весенний рейтинг",
            event_date=date(2026, 3, 15),
            player_card_ids=[card_id, card_id],
        )


def test_rating_write_trims_name() -> None:
    body = RatingWrite(
        name="  Клубный рейтинг  ",
        event_date=date(2026, 4, 1),
        player_card_ids=[],
    )
    assert body.name == "Клубный рейтинг"


def test_rating_patch_allows_partial_update() -> None:
    body = RatingPatch(name="Новое название")
    dumped = body.model_dump(exclude_unset=True)
    assert dumped == {"name": "Новое название"}


def test_rating_table_bonus_plus_minus_and_roles(monkeypatch: pytest.MonkeyPatch) -> None:
    player_id = uuid.uuid4()
    participant = SimpleNamespace(
        player_card_id=player_id,
        player_card=SimpleNamespace(
            nickname="Dendi",
            first_name="A",
            last_name="B",
            club=None,
            photo_urls=[],
        ),
    )
    game_1 = _game_with_seats(
        player_id,
        player_seat=6,
        player_role=GameRole.SHERIFF,
        winner_side=RatingWinnerSide.RED,
        bonus_points=0.5,
        total_points=2.0,
        best_move=["1", "", ""],
        seat_roles=_STANDARD_SEAT_ROLES,
    )
    game_2 = _game_with_seats(
        player_id,
        player_seat=3,
        player_role=GameRole.DON,
        winner_side=RatingWinnerSide.BLACK,
        bonus_points=-0.3,
        total_points=1.0,
        best_move=["", "", ""],
        seat_roles=_STANDARD_SEAT_ROLES,
    )
    game_3 = _game_with_seats(
        player_id,
        player_seat=4,
        player_role=GameRole.PEACEFUL,
        winner_side=RatingWinnerSide.RED,
        bonus_points=1.0,
        total_points=3.0,
        best_move=["1", "2", ""],
        seat_roles=_STANDARD_SEAT_ROLES,
    )
    fake_rating = SimpleNamespace(participants=[participant], games=[game_1, game_2, game_3])

    async def _fake_get_owned_rating(*_args, **_kwargs):
        return fake_rating

    monkeypatch.setattr(ratings_app, "_get_owned_rating", _fake_get_owned_rating)
    err, table = asyncio.run(
        ratings_app.get_rating_table(
            session=SimpleNamespace(),
            owner_user_id=uuid.uuid4(),
            rating_id=uuid.uuid4(),
        )
    )

    assert err is None
    assert table is not None
    row = table.rows[0]
    assert row.games_total == 3
    assert row.games_red == 2
    assert row.games_black == 1
    assert row.games_sheriff == 1
    assert row.games_don == 1
    assert row.games_peaceful == 1
    assert row.bonus_points_plus_sum == 1.5
    assert row.bonus_points_minus_sum == 0.3
    assert row.bonus_points_sum == 1.2
    assert row.bonus_sheriff_plus_sum == 0.5
    assert row.bonus_sheriff_minus_sum == 0
    assert row.bonus_don_plus_sum == 0
    assert row.bonus_don_minus_sum == 0.3
    assert row.bonus_peaceful_plus_sum == 1.0
    assert row.bonus_peaceful_minus_sum == 0
    assert row.bonus_mafia_plus_sum == 0
    assert row.bonus_mafia_minus_sum == 0
    assert row.best_move_count_0 == 0
    assert row.best_move_count_1 == 2
    assert row.best_move_count_2 == 0
    assert row.best_move_count_3 == 0
    assert row.best_move_sum == 2


def test_rating_table_bonus_all_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    player_id = uuid.uuid4()
    participant = SimpleNamespace(
        player_card_id=player_id,
        player_card=SimpleNamespace(
            nickname="Zero",
            first_name="Z",
            last_name="E",
            club=None,
            photo_urls=[],
        ),
    )
    game = _game_with_seats(
        player_id,
        player_seat=4,
        player_role=GameRole.PEACEFUL,
        winner_side=RatingWinnerSide.RED,
        bonus_points=0.0,
        total_points=0.0,
        best_move=["", "", ""],
        seat_roles=_STANDARD_SEAT_ROLES,
    )
    fake_rating = SimpleNamespace(participants=[participant], games=[game])

    async def _fake_get_owned_rating(*_args, **_kwargs):
        return fake_rating

    monkeypatch.setattr(ratings_app, "_get_owned_rating", _fake_get_owned_rating)
    _, table = asyncio.run(
        ratings_app.get_rating_table(
            session=SimpleNamespace(),
            owner_user_id=uuid.uuid4(),
            rating_id=uuid.uuid4(),
        )
    )
    assert table is not None
    row = table.rows[0]
    assert row.bonus_points_plus_sum == 0
    assert row.bonus_points_minus_sum == 0
    assert row.bonus_points_sum == 0
    assert row.best_move_count_0 == 0
    assert row.best_move_count_1 == 0
    assert row.best_move_count_2 == 0
    assert row.best_move_count_3 == 0
    assert row.best_move_sum == 0


def test_rating_table_bonus_only_negative(monkeypatch: pytest.MonkeyPatch) -> None:
    player_id = uuid.uuid4()
    participant = SimpleNamespace(
        player_card_id=player_id,
        player_card=SimpleNamespace(
            nickname="Minus",
            first_name="M",
            last_name="N",
            club=None,
            photo_urls=[],
        ),
    )
    game = _game_with_seats(
        player_id,
        player_seat=1,
        player_role=GameRole.MAFIA,
        winner_side=RatingWinnerSide.BLACK,
        bonus_points=-2.0,
        total_points=-1.0,
        best_move=["1", "", ""],
        seat_roles=_STANDARD_SEAT_ROLES,
    )
    fake_rating = SimpleNamespace(participants=[participant], games=[game])

    async def _fake_get_owned_rating(*_args, **_kwargs):
        return fake_rating

    monkeypatch.setattr(ratings_app, "_get_owned_rating", _fake_get_owned_rating)
    _, table = asyncio.run(
        ratings_app.get_rating_table(
            session=SimpleNamespace(),
            owner_user_id=uuid.uuid4(),
            rating_id=uuid.uuid4(),
        )
    )
    assert table is not None
    row = table.rows[0]
    assert row.bonus_points_plus_sum == 0
    assert row.bonus_points_minus_sum == 2.0
    assert row.bonus_points_sum == -2.0
    assert row.bonus_mafia_plus_sum == 0
    assert row.bonus_mafia_minus_sum == 2.0
    assert row.best_move_count_1 == 1
    assert row.best_move_sum == 1


def test_rating_table_sheriff_role_bonus_split(monkeypatch: pytest.MonkeyPatch) -> None:
    player_id = uuid.uuid4()
    participant = SimpleNamespace(
        player_card_id=player_id,
        player_card=SimpleNamespace(
            nickname="Sheriff",
            first_name="S",
            last_name="H",
            club=None,
            photo_urls=[],
        ),
    )
    games = [
        _game_with_seats(
            player_id,
            player_seat=6,
            player_role=GameRole.SHERIFF,
            winner_side=RatingWinnerSide.RED,
            bonus_points=1.0,
            total_points=2.0,
            best_move=["1", "3", "5"],
            seat_roles=_STANDARD_SEAT_ROLES,
        ),
        _game_with_seats(
            player_id,
            player_seat=6,
            player_role=GameRole.SHERIFF,
            winner_side=RatingWinnerSide.RED,
            bonus_points=1.0,
            total_points=2.0,
            best_move=["1", "3", ""],
            seat_roles=_STANDARD_SEAT_ROLES,
        ),
        _game_with_seats(
            player_id,
            player_seat=6,
            player_role=GameRole.SHERIFF,
            winner_side=RatingWinnerSide.BLACK,
            bonus_points=-0.5,
            total_points=0.0,
            best_move=["1", "", ""],
            seat_roles=_STANDARD_SEAT_ROLES,
        ),
    ]
    fake_rating = SimpleNamespace(participants=[participant], games=games)

    async def _fake_get_owned_rating(*_args, **_kwargs):
        return fake_rating

    monkeypatch.setattr(ratings_app, "_get_owned_rating", _fake_get_owned_rating)
    _, table = asyncio.run(
        ratings_app.get_rating_table(
            session=SimpleNamespace(),
            owner_user_id=uuid.uuid4(),
            rating_id=uuid.uuid4(),
        )
    )
    assert table is not None
    row = table.rows[0]
    assert row.games_sheriff == 3
    assert row.bonus_sheriff_plus_sum == 2.0
    assert row.bonus_sheriff_minus_sum == 0.5
    assert row.best_move_count_0 == 0
    assert row.best_move_count_1 == 1
    assert row.best_move_count_2 == 1
    assert row.best_move_count_3 == 1
    assert row.best_move_sum == 3


def test_sync_rating_from_lobby_copies_best_move(monkeypatch: pytest.MonkeyPatch) -> None:
    player_id = uuid.uuid4()
    owner_id = uuid.uuid4()
    rating_id = uuid.uuid4()
    lobby_id = uuid.uuid4()

    rating = SimpleNamespace(participants=[SimpleNamespace(player_card_id=player_id)])
    member = SimpleNamespace(
        player_card_id=player_id,
        game_role=GameRole.SHERIFF,
        bonus_points=1.0,
        best_move=[" 1 ", "", "3"],
        seat_order=0,
        joined_at=1,
    )
    lobby = SimpleNamespace(
        id=lobby_id,
        host_user_id=owner_id,
        title="Лобби",
        member_links=[member],
    )

    loaded_game = SimpleNamespace(
        id=uuid.uuid4(),
        rating_id=rating_id,
        title="Лобби",
        played_at=date(2026, 7, 29),
        winner_side=RatingWinnerSide.RED,
        source="lobby_sync",
        lobby_id=lobby_id,
        created_at="2026-07-29T00:00:00Z",
        results=[
            SimpleNamespace(
                player_card_id=player_id,
                role=GameRole.SHERIFF,
                bonus_points=1.0,
                total_points=2.0,
                best_move=["1", "", "3"],
                player_card=SimpleNamespace(
                    nickname="Dendi",
                    first_name="A",
                    last_name="B",
                ),
            )
        ],
    )

    class _ExecResult:
        def __init__(self, one_or_none=None, one=None):
            self._one_or_none = one_or_none
            self._one = one

        def scalar_one_or_none(self):
            return self._one_or_none

        def scalar_one(self):
            return self._one

    class _FakeSession:
        def __init__(self):
            self.added = []
            self.calls = 0

        async def execute(self, _stmt):
            self.calls += 1
            if self.calls == 1:
                return _ExecResult(one_or_none=lobby)
            return _ExecResult(one=loaded_game)

        def add(self, obj):
            self.added.append(obj)

        async def flush(self):
            return None

        async def commit(self):
            return None

    async def _fake_get_owned_rating(*_args, **_kwargs):
        return rating

    monkeypatch.setattr(ratings_app, "_get_owned_rating", _fake_get_owned_rating)
    session = _FakeSession()
    body = RatingSyncLobbyBody(
        lobby_id=lobby_id,
        played_at=date(2026, 7, 29),
        winner_side=RatingWinnerSide.RED,
        total_points=[{"player_card_id": player_id, "total_points": 2.0}],
    )
    err, game = asyncio.run(
        ratings_app.sync_rating_from_lobby(
            session=session,
            owner_user_id=owner_id,
            rating_id=rating_id,
            body=body,
        )
    )

    assert err is None
    assert game is not None
    added_results = [item for item in session.added if isinstance(item, RatingGameResult)]
    assert len(added_results) == 1
    assert added_results[0].best_move == ["1", "", "3"]


def test_delete_rating_game_not_found() -> None:
    class _ExecResult:
        def scalar_one_or_none(self):
            return None

    class _FakeSession:
        async def execute(self, _stmt):
            return _ExecResult()

    err, deleted = asyncio.run(
        ratings_app.delete_rating_game(
            session=_FakeSession(),  # type: ignore[arg-type]
            owner_user_id=uuid.uuid4(),
            rating_id=uuid.uuid4(),
            game_id=uuid.uuid4(),
        )
    )
    assert err == "not_found"
    assert deleted is False


def test_delete_rating_game_success() -> None:
    game = SimpleNamespace(id=uuid.uuid4())

    class _ExecResult:
        def scalar_one_or_none(self):
            return game

    class _FakeSession:
        def __init__(self):
            self.deleted = None
            self.committed = False

        async def execute(self, _stmt):
            return _ExecResult()

        async def delete(self, row):
            self.deleted = row

        async def commit(self):
            self.committed = True

    session = _FakeSession()
    err, deleted = asyncio.run(
        ratings_app.delete_rating_game(
            session=session,  # type: ignore[arg-type]
            owner_user_id=uuid.uuid4(),
            rating_id=uuid.uuid4(),
            game_id=game.id,
        )
    )
    assert err is None
    assert deleted is True
    assert session.deleted is game
    assert session.committed is True


def test_remove_rating_participant_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_get_owned_rating(*_args, **_kwargs):
        return None

    monkeypatch.setattr(ratings_app, "_get_owned_rating", _fake_get_owned_rating)
    err, row = asyncio.run(
        ratings_app.remove_rating_participant(
            session=SimpleNamespace(),  # type: ignore[arg-type]
            owner_user_id=uuid.uuid4(),
            rating_id=uuid.uuid4(),
            player_card_id=uuid.uuid4(),
        )
    )
    assert err == "not_found"
    assert row is None


def test_remove_rating_participant_with_games_still_deletes(monkeypatch: pytest.MonkeyPatch) -> None:
    player_id = uuid.uuid4()
    participant = SimpleNamespace(player_card_id=player_id, sort_order=0)
    fake_rating = SimpleNamespace(
        id=uuid.uuid4(),
        owner_user_id=uuid.uuid4(),
        name="R",
        event_date=date(2026, 8, 9),
        created_at=datetime(2026, 8, 9),
        updated_at=datetime(2026, 8, 9),
        participants=[participant],
        games=[
            SimpleNamespace(
                results=[SimpleNamespace(player_card_id=player_id)],
            )
        ],
    )

    async def _fake_get_owned_rating(*_args, **_kwargs):
        return fake_rating

    monkeypatch.setattr(ratings_app, "_get_owned_rating", _fake_get_owned_rating)

    class _FakeSession:
        def __init__(self):
            self.committed = False

        async def commit(self):
            self.committed = True

    session = _FakeSession()
    err, row = asyncio.run(
        ratings_app.remove_rating_participant(
            session=session,  # type: ignore[arg-type]
            owner_user_id=uuid.uuid4(),
            rating_id=uuid.uuid4(),
            player_card_id=player_id,
        )
    )
    assert err is None
    assert row is not None
    assert session.committed is True
    assert fake_rating.participants == []


def test_remove_rating_participant_success(monkeypatch: pytest.MonkeyPatch) -> None:
    first_id = uuid.uuid4()
    second_id = uuid.uuid4()
    first = SimpleNamespace(
        player_card_id=first_id,
        sort_order=0,
        player_card=SimpleNamespace(nickname="F", first_name="F", last_name="F", club=None),
        id=uuid.uuid4(),
    )
    second = SimpleNamespace(
        player_card_id=second_id,
        sort_order=1,
        player_card=SimpleNamespace(nickname="S", first_name="S", last_name="S", club=None),
        id=uuid.uuid4(),
    )
    fake_rating = SimpleNamespace(
        id=uuid.uuid4(),
        owner_user_id=uuid.uuid4(),
        name="R",
        event_date=date(2026, 8, 9),
        participants=[first, second],
        games=[],
        created_at=datetime(2026, 8, 9),
        updated_at=datetime(2026, 8, 9),
    )

    calls = {"count": 0}

    async def _fake_get_owned_rating(*_args, **_kwargs):
        calls["count"] += 1
        return fake_rating

    monkeypatch.setattr(ratings_app, "_get_owned_rating", _fake_get_owned_rating)

    class _FakeSession:
        def __init__(self):
            self.committed = False

        async def commit(self):
            self.committed = True

    session = _FakeSession()
    err, row = asyncio.run(
        ratings_app.remove_rating_participant(
            session=session,  # type: ignore[arg-type]
            owner_user_id=fake_rating.owner_user_id,
            rating_id=fake_rating.id,
            player_card_id=first_id,
        )
    )
    assert err is None
    assert row is not None
    assert session.committed is True
    assert len(fake_rating.participants) == 1
    assert fake_rating.participants[0].player_card_id == second_id
    assert fake_rating.participants[0].sort_order == 0


def test_update_rating_game_not_found() -> None:
    class _ExecResult:
        def scalar_one_or_none(self):
            return None

    class _FakeSession:
        async def execute(self, _stmt):
            return _ExecResult()

    err, row = asyncio.run(
        ratings_app.update_rating_game(
            session=_FakeSession(),  # type: ignore[arg-type]
            owner_user_id=uuid.uuid4(),
            rating_id=uuid.uuid4(),
            game_id=uuid.uuid4(),
            body=ratings_app.RatingGamePatch(title="Новая игра"),
        )
    )
    assert err == "not_found"
    assert row is None


def test_update_rating_game_rejects_player_outside_rating() -> None:
    in_rating_id = uuid.uuid4()
    out_of_rating_id = uuid.uuid4()

    game = SimpleNamespace(
        id=uuid.uuid4(),
        rating_id=uuid.uuid4(),
        title="Старая игра",
        played_at=date(2026, 8, 1),
        winner_side=RatingWinnerSide.RED,
        source=RatingGameSource.MANUAL,
        lobby_id=None,
        created_at=datetime(2026, 8, 1),
        rating=SimpleNamespace(
            participants=[
                SimpleNamespace(
                    player_card_id=in_rating_id,
                    player_card=SimpleNamespace(
                        nickname="A",
                        first_name="A",
                        last_name="A",
                    ),
                )
            ]
        ),
        results=[
            SimpleNamespace(
                player_card_id=in_rating_id,
                role=GameRole.PEACEFUL,
                bonus_points=0.0,
                total_points=1.0,
                best_move=["", "", ""],
                player_card=SimpleNamespace(
                    nickname="A",
                    first_name="A",
                    last_name="A",
                ),
            )
        ],
    )

    class _ExecResult:
        def scalar_one_or_none(self):
            return game

    class _FakeSession:
        def __init__(self):
            self.committed = False

        async def execute(self, _stmt):
            return _ExecResult()

        async def commit(self):
            self.committed = True

    session = _FakeSession()
    err, row = asyncio.run(
        ratings_app.update_rating_game(
            session=session,  # type: ignore[arg-type]
            owner_user_id=uuid.uuid4(),
            rating_id=uuid.uuid4(),
            game_id=game.id,
            body=ratings_app.RatingGamePatch(
                results=[
                    {
                        "player_card_id": out_of_rating_id,
                        "role": GameRole.MAFIA,
                        "bonus_points": 0.0,
                        "total_points": 1.0,
                    }
                ]
            ),
        )
    )
    assert err == "player_not_in_rating"
    assert row is None
    assert session.committed is False


def test_update_rating_game_success() -> None:
    first_id = uuid.uuid4()
    second_id = uuid.uuid4()
    played_at = date(2026, 8, 10)

    game = SimpleNamespace(
        id=uuid.uuid4(),
        rating_id=uuid.uuid4(),
        title="Старая игра",
        played_at=date(2026, 8, 1),
        winner_side=RatingWinnerSide.RED,
        source=RatingGameSource.MANUAL,
        lobby_id=None,
        created_at=datetime(2026, 8, 1),
        rating=SimpleNamespace(
            participants=[
                SimpleNamespace(
                    player_card_id=first_id,
                    player_card=SimpleNamespace(
                        nickname="First",
                        first_name="F",
                        last_name="I",
                    ),
                ),
                SimpleNamespace(
                    player_card_id=second_id,
                    player_card=SimpleNamespace(
                        nickname="Second",
                        first_name="S",
                        last_name="E",
                    ),
                ),
            ]
        ),
        results=[
            SimpleNamespace(
                player_card_id=first_id,
                role=GameRole.PEACEFUL,
                bonus_points=0.0,
                total_points=1.0,
                best_move=["", "", ""],
                player_card=SimpleNamespace(
                    nickname="First",
                    first_name="F",
                    last_name="I",
                ),
            )
        ],
    )

    loaded_game = SimpleNamespace(
        id=game.id,
        rating_id=game.rating_id,
        title="Новая игра",
        played_at=played_at,
        winner_side=RatingWinnerSide.BLACK,
        source=RatingGameSource.MANUAL,
        lobby_id=None,
        created_at=datetime(2026, 8, 1),
        results=[
            SimpleNamespace(
                player_card_id=first_id,
                role=GameRole.MAFIA,
                bonus_points=0.5,
                total_points=1.5,
                best_move=["1", "", ""],
                player_card=SimpleNamespace(
                    nickname="First",
                    first_name="F",
                    last_name="I",
                ),
            ),
            SimpleNamespace(
                player_card_id=second_id,
                role=GameRole.DON,
                bonus_points=0.0,
                total_points=1.0,
                best_move=["", "", ""],
                player_card=SimpleNamespace(
                    nickname="Second",
                    first_name="S",
                    last_name="E",
                ),
            ),
        ],
    )

    class _ExecResult:
        def __init__(self, one_or_none=None, one=None):
            self._one_or_none = one_or_none
            self._one = one

        def scalar_one_or_none(self):
            return self._one_or_none

        def scalar_one(self):
            return self._one

    class _FakeSession:
        def __init__(self):
            self.committed = False
            self.calls = 0

        async def execute(self, _stmt):
            self.calls += 1
            if self.calls == 1:
                return _ExecResult(one_or_none=game)
            return _ExecResult(one=loaded_game)

        async def commit(self):
            self.committed = True

    session = _FakeSession()
    err, row = asyncio.run(
        ratings_app.update_rating_game(
            session=session,  # type: ignore[arg-type]
            owner_user_id=uuid.uuid4(),
            rating_id=uuid.uuid4(),
            game_id=game.id,
            body=ratings_app.RatingGamePatch(
                title="Новая игра",
                played_at=played_at,
                winner_side=RatingWinnerSide.BLACK,
                results=[
                    {
                        "player_card_id": first_id,
                        "role": GameRole.MAFIA,
                        "bonus_points": 0.5,
                        "total_points": 1.5,
                        "best_move": ["1", "", ""],
                    },
                    {
                        "player_card_id": second_id,
                        "role": GameRole.DON,
                        "bonus_points": 0.0,
                        "total_points": 1.0,
                        "best_move": ["", "", ""],
                    },
                ],
            ),
        )
    )
    assert err is None
    assert row is not None
    assert session.committed is True
    assert game.title == "Новая игра"
    assert game.played_at == played_at
    assert game.winner_side == RatingWinnerSide.BLACK
    assert len(game.results) == 2
    assert game.results[0].role == GameRole.MAFIA
    assert game.results[0].best_move == ["1", "", ""]
    assert game.results[1].role == GameRole.DON
    assert row.title == "Новая игра"
    assert len(row.results) == 2


def test_rating_game_best_move_patch_normalizes_values() -> None:
    player_id = uuid.uuid4()
    body = RatingGameBestMovePatch(
        results=[
            {
                "player_card_id": player_id,
                "best_move": [" 1 ", "  ", "3", "ignored"],
            }
        ]
    )
    assert body.results[0].best_move == ["1", "", "3"]


def test_rating_game_best_move_patch_sanitizes_invalid_and_duplicates() -> None:
    player_id = uuid.uuid4()
    body = RatingGameBestMovePatch(
        results=[
            {
                "player_card_id": player_id,
                "best_move": [" 2 ", "2", "x", "0", "-1", "5"],
            }
        ]
    )
    assert body.results[0].best_move == ["2", "", ""]


def test_rating_game_best_move_patch_rejects_duplicate_players() -> None:
    player_id = uuid.uuid4()
    with pytest.raises(ValidationError):
        RatingGameBestMovePatch(
            results=[
                {"player_card_id": player_id, "best_move": ["1", "", ""]},
                {"player_card_id": player_id, "best_move": ["2", "", ""]},
            ]
        )


def test_update_rating_game_best_move_not_found() -> None:
    class _ExecResult:
        def scalar_one_or_none(self):
            return None

    class _FakeSession:
        async def execute(self, _stmt):
            return _ExecResult()

    err, row = asyncio.run(
        ratings_app.update_rating_game_best_move(
            session=_FakeSession(),  # type: ignore[arg-type]
            owner_user_id=uuid.uuid4(),
            rating_id=uuid.uuid4(),
            game_id=uuid.uuid4(),
            body=RatingGameBestMovePatch(
                results=[{"player_card_id": uuid.uuid4(), "best_move": ["1", "", ""]}]
            ),
        )
    )
    assert err == "not_found"
    assert row is None


def test_update_rating_game_best_move_player_not_in_game() -> None:
    player_id = uuid.uuid4()
    missing_player_id = uuid.uuid4()
    game = SimpleNamespace(
        id=uuid.uuid4(),
        rating_id=uuid.uuid4(),
        title="Игра",
        played_at=date(2026, 8, 1),
        winner_side=RatingWinnerSide.RED,
        source=RatingGameSource.MANUAL,
        lobby_id=None,
        created_at=datetime(2026, 8, 1),
        results=[
            SimpleNamespace(
                player_card_id=player_id,
                role=GameRole.PEACEFUL,
                bonus_points=0.0,
                total_points=1.0,
                best_move=["", "", ""],
                player_card=SimpleNamespace(
                    nickname="Player",
                    first_name="P",
                    last_name="L",
                ),
            )
        ],
    )

    class _ExecResult:
        def scalar_one_or_none(self):
            return game

    class _FakeSession:
        def __init__(self):
            self.committed = False

        async def execute(self, _stmt):
            return _ExecResult()

        async def commit(self):
            self.committed = True

    session = _FakeSession()
    err, row = asyncio.run(
        ratings_app.update_rating_game_best_move(
            session=session,  # type: ignore[arg-type]
            owner_user_id=uuid.uuid4(),
            rating_id=uuid.uuid4(),
            game_id=game.id,
            body=RatingGameBestMovePatch(
                results=[{"player_card_id": missing_player_id, "best_move": ["2", "", ""]}]
            ),
        )
    )
    assert err == "player_not_in_game"
    assert row is None
    assert session.committed is False


def test_update_rating_game_best_move_success() -> None:
    player_id = uuid.uuid4()
    game = SimpleNamespace(
        id=uuid.uuid4(),
        rating_id=uuid.uuid4(),
        title="Игра",
        played_at=date(2026, 8, 1),
        winner_side=RatingWinnerSide.BLACK,
        source=RatingGameSource.MANUAL,
        lobby_id=None,
        created_at=datetime(2026, 8, 1),
        results=[
            SimpleNamespace(
                player_card_id=player_id,
                role=GameRole.SHERIFF,
                bonus_points=0.5,
                total_points=1.5,
                best_move=["", "", ""],
                player_card=SimpleNamespace(
                    nickname="Sheriff",
                    first_name="S",
                    last_name="H",
                ),
            )
        ],
    )

    class _ExecResult:
        def scalar_one_or_none(self):
            return game

    class _FakeSession:
        def __init__(self):
            self.committed = False

        async def execute(self, _stmt):
            return _ExecResult()

        async def commit(self):
            self.committed = True

    session = _FakeSession()
    err, row = asyncio.run(
        ratings_app.update_rating_game_best_move(
            session=session,  # type: ignore[arg-type]
            owner_user_id=uuid.uuid4(),
            rating_id=uuid.uuid4(),
            game_id=game.id,
            body=RatingGameBestMovePatch(
                results=[{"player_card_id": player_id, "best_move": [" 4 ", "1", " "]}]
            ),
        )
    )
    assert err is None
    assert row is not None
    assert session.committed is True
    assert game.results[0].best_move == ["4", "1", ""]
    assert row.results[0].best_move == ["4", "1", ""]
