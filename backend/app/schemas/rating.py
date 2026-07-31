import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.db.base import GameRole, RatingGameSource, RatingWinnerSide


class RatingWrite(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    event_date: date
    player_card_ids: list[uuid.UUID] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Название рейтинга не может быть пустым")
        return trimmed

    @field_validator("player_card_ids")
    @classmethod
    def unique_player_cards(cls, value: list[uuid.UUID]) -> list[uuid.UUID]:
        if len(value) != len(set(value)):
            raise ValueError("Игрок не может быть добавлен в рейтинг дважды")
        return value


class RatingPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    event_date: date | None = None
    player_card_ids: list[uuid.UUID] | None = None

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Название рейтинга не может быть пустым")
        return trimmed

    @field_validator("player_card_ids")
    @classmethod
    def unique_player_cards(
        cls, value: list[uuid.UUID] | None
    ) -> list[uuid.UUID] | None:
        if value is None:
            return None
        if len(value) != len(set(value)):
            raise ValueError("Игрок не может быть добавлен в рейтинг дважды")
        return value


class RatingAddParticipantsBody(BaseModel):
    player_card_ids: list[uuid.UUID] = Field(min_length=1)

    @field_validator("player_card_ids")
    @classmethod
    def unique_player_cards(cls, value: list[uuid.UUID]) -> list[uuid.UUID]:
        if len(value) != len(set(value)):
            raise ValueError("Игрок не может быть добавлен в рейтинг дважды")
        return value


class RatingParticipantPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    player_card_id: uuid.UUID
    sort_order: int
    nickname: str
    first_name: str
    last_name: str
    club: str | None


class RatingGameResultWrite(BaseModel):
    player_card_id: uuid.UUID
    role: GameRole
    bonus_points: float = Field(default=0, ge=-999.9, le=999.9, multiple_of=0.1)
    total_points: float = Field(ge=-999.9, le=999.9, multiple_of=0.1)
    best_move: list[str] = Field(default_factory=lambda: ["", "", ""])

    @field_validator("best_move")
    @classmethod
    def normalize_best_move(cls, value: list[str]) -> list[str]:
        normalized = [(item or "").strip() for item in value[:3]]
        normalized.extend([""] * (3 - len(normalized)))
        return normalized


class RatingGameWrite(BaseModel):
    title: str = Field(default="", max_length=255)
    played_at: date
    winner_side: RatingWinnerSide
    results: list[RatingGameResultWrite] = Field(min_length=1)

    @field_validator("title")
    @classmethod
    def strip_title(cls, value: str) -> str:
        return value.strip()

    @field_validator("results")
    @classmethod
    def unique_players(cls, value: list[RatingGameResultWrite]) -> list[RatingGameResultWrite]:
        ids = [entry.player_card_id for entry in value]
        if len(ids) != len(set(ids)):
            raise ValueError("Игрок не может быть указан в одной игре дважды")
        return value


class RatingTotalPointEntry(BaseModel):
    player_card_id: uuid.UUID
    total_points: float = Field(ge=-999.9, le=999.9, multiple_of=0.1)


class RatingSyncLobbyBody(BaseModel):
    lobby_id: uuid.UUID
    played_at: date
    winner_side: RatingWinnerSide
    title: str = Field(default="", max_length=255)
    total_points: list[RatingTotalPointEntry] = Field(default_factory=list)

    @field_validator("title")
    @classmethod
    def strip_title(cls, value: str) -> str:
        return value.strip()

    @field_validator("total_points")
    @classmethod
    def unique_total_points(
        cls, value: list[RatingTotalPointEntry]
    ) -> list[RatingTotalPointEntry]:
        ids = [entry.player_card_id for entry in value]
        if len(ids) != len(set(ids)):
            raise ValueError("Игрок не может быть указан в total_points дважды")
        return value


class RatingGameResultPublic(BaseModel):
    player_card_id: uuid.UUID
    nickname: str
    first_name: str | None = None
    last_name: str | None = None
    role: GameRole
    bonus_points: float
    total_points: float
    best_move: list[str]


class RatingGamePublic(BaseModel):
    id: uuid.UUID
    rating_id: uuid.UUID
    title: str
    played_at: date
    winner_side: RatingWinnerSide
    source: RatingGameSource
    lobby_id: uuid.UUID | None = None
    created_at: datetime
    results: list[RatingGameResultPublic]


class RatingGameListItem(BaseModel):
    id: uuid.UUID
    title: str
    played_at: date
    winner_side: RatingWinnerSide
    players_count: int
    source: RatingGameSource
    lobby_id: uuid.UUID | None = None
    created_at: datetime


class RatingGameListResponse(BaseModel):
    rating_id: uuid.UUID
    total: int
    items: list[RatingGameListItem]


class RatingTableRow(BaseModel):
    player_card_id: uuid.UUID
    nickname: str
    first_name: str
    last_name: str
    club: str | None
    photo_url: str | None = None
    games_total: int = 0
    games_black: int = 0
    games_red: int = 0
    games_mafia: int = 0
    games_peaceful: int = 0
    games_sheriff: int = 0
    games_don: int = 0
    wins_total: int = 0
    bonus_peaceful_plus_sum: float = 0
    bonus_peaceful_minus_sum: float = 0
    bonus_mafia_plus_sum: float = 0
    bonus_mafia_minus_sum: float = 0
    bonus_don_plus_sum: float = 0
    bonus_don_minus_sum: float = 0
    bonus_sheriff_plus_sum: float = 0
    bonus_sheriff_minus_sum: float = 0
    bonus_points_plus_sum: float = 0
    bonus_points_minus_sum: float = 0
    bonus_points_sum: float = 0
    best_move_sum: float = 0
    best_move_count_0: int = 0
    best_move_count_1: int = 0
    best_move_count_2: int = 0
    best_move_count_3: int = 0
    total_points_sum: float = 0
    total_points_mafia_sum: float = 0
    total_points_peaceful_sum: float = 0
    total_points_sheriff_sum: float = 0
    total_points_don_sum: float = 0
    avg_points_mafia: float = 0
    avg_points_peaceful: float = 0
    avg_points_sheriff: float = 0
    avg_points_don: float = 0
    is_best_mafia: bool = False
    is_best_peaceful: bool = False
    is_best_sheriff: bool = False
    is_best_don: bool = False
    # Совместимые дубли для фронта, если кнопка/таблица ожидает другие ключи.
    games_count: int = 0
    black_games_count: int = 0
    red_games_count: int = 0
    games_as_black: int = 0
    games_as_red: int = 0
    sheriff_games_count: int = 0
    don_games_count: int = 0
    games_as_sheriff: int = 0
    games_as_don: int = 0
    mafia_games_count: int = 0
    peaceful_games_count: int = 0
    games_as_mafia: int = 0
    games_as_peaceful: int = 0
    bonus_peaceful_plus_total: float = 0
    bonus_peaceful_minus_total: float = 0
    bonus_mafia_plus_total: float = 0
    bonus_mafia_minus_total: float = 0
    bonus_don_plus_total: float = 0
    bonus_don_minus_total: float = 0
    bonus_sheriff_plus_total: float = 0
    bonus_sheriff_minus_total: float = 0
    bonus_points_plus_total: float = 0
    bonus_points_minus_total: float = 0
    bonus_points_total: float = 0
    total_points_total: float = 0


class RatingTableResponse(BaseModel):
    rating_id: uuid.UUID
    rows: list[RatingTableRow]


class RatingPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_user_id: uuid.UUID
    name: str
    event_date: date
    participants: list[RatingParticipantPublic]
    created_at: datetime
    updated_at: datetime


class RatingListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    event_date: date
    participant_count: int
    created_at: datetime
    updated_at: datetime
