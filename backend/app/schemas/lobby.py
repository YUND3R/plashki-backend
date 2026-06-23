import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.db.base import GameRole, GameStatus, LOBBY_MAX_PLAYERS, OverlayDesign, Subscription


class LobbiesTotalResponse(BaseModel):
    total: int


class CreateGameLobbyBody(BaseModel):
    max_players: int = Field(
        default=LOBBY_MAX_PLAYERS,
        ge=1,
        le=LOBBY_MAX_PLAYERS,
        description="Вместимость лобби (не больше LOBBY_MAX_PLAYERS).",
    )
    title: str = Field(
        default="Лобби",
        min_length=1,
        max_length=120,
        description="Название лобби для отображения пользователю.",
    )


class ImportGomafiaTournamentBody(BaseModel):
    url: str = Field(
        min_length=10,
        max_length=1024,
        description="Ссылка на турнир gomafia.pro (страница с tab=games).",
    )


class ImportedLobbyInfo(BaseModel):
    lobby_id: uuid.UUID
    title: str
    players_count: int


class ImportGomafiaTournamentResponse(BaseModel):
    source_url: str
    created_lobbies: list[ImportedLobbyInfo]


class SelectImportedLobbyTableBody(BaseModel):
    key: str = Field(
        min_length=1,
        max_length=120,
        description="Ключ варианта стола (из imported_state.variants[].key).",
    )


class ImportedLobbyVariant(BaseModel):
    key: str
    title: str
    tour_no: int
    table_label: str
    players_count: int


class ImportedLobbyState(BaseModel):
    source_url: str
    current_key: str
    variants: list[ImportedLobbyVariant]


class ImportedTournamentParticipant(BaseModel):
    player_card_id: uuid.UUID
    nickname: str


class ImportedTournamentParticipantsResponse(BaseModel):
    lobby_id: uuid.UUID
    source_url: str
    participants: list[ImportedTournamentParticipant]


class SetGameRoleBody(BaseModel):
    game_role: GameRole


class SetLobbyStatusBody(BaseModel):
    status: GameStatus


class SetOverlayDesignBody(BaseModel):
    overlay_design: OverlayDesign


class SetActiveOverlayScreenBody(BaseModel):
    screen_key: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$",
        description="Ключ активного экрана для OBS (например: lobby, roles, scoreboard).",
    )


class SetActiveOverlayLobbyBody(BaseModel):
    lobby_id: str = Field(
        min_length=1,
        max_length=64,
        description="UUID лобби, которое станет активным для OBS live-ссылки.",
    )


class ActiveOverlayLobbyResponse(BaseModel):
    active_lobby_id: uuid.UUID | None
    updated_at: datetime


class OverlayLiveStateResponse(BaseModel):
    active_lobby_id: uuid.UUID | None
    active_overlay_screen: str
    selected_overlay_design: OverlayDesign


class SetSheriffCheckBody(BaseModel):
    sheriff_check: list[str] = Field(
        min_length=5,
        max_length=5,
        description="5 отметок sheriff check, например ['X','X','X','X','X']",
    )


class SetBestMoveBody(BaseModel):
    best_move: list[str] = Field(
        min_length=3,
        max_length=3,
        description="3 отметки best move, например ['X','X','X']",
    )


class LobbyOverlayDesignOption(BaseModel):
    code: OverlayDesign
    title: str
    required_subscription: Subscription
    animations_supported: bool
    selectable: bool


class LobbyOverlayDesignsResponse(BaseModel):
    lobby_id: uuid.UUID
    selected_overlay_design: OverlayDesign
    options: list[LobbyOverlayDesignOption]


class OverlayDesignCatalogResponse(BaseModel):
    options: list[LobbyOverlayDesignOption]


class OverlayPlayerState(BaseModel):
    seat_order: int
    membership_id: uuid.UUID
    nickname: str
    lobby_photo_url: str | None = None
    game_role: str | None
    status: str | None


class LobbyOverlayStateResponse(BaseModel):
    lobby_id: uuid.UUID
    selected_overlay_design: OverlayDesign
    active_overlay_screen: str
    design_catalog: list[LobbyOverlayDesignOption]
    sheriff_check: list[str]
    best_move: list[str]
    players: list[OverlayPlayerState]


class SwapLobbySeatsBody(BaseModel):
    """Обмен местами двух игроков в лобби (по id строки lobby_membership)."""

    membership_id_a: uuid.UUID
    membership_id_b: uuid.UUID


class ReplaceLobbyMemberBody(BaseModel):
    """Сменить карточку игрока у места в лобби (id строки — membership_id из GET лобби)."""

    player_card_id: uuid.UUID


class SetLobbyMemberDisplayPhotoBody(BaseModel):
    """Какое фото с карточки показывать в лобби (URL из списка photo_urls карточки)."""

    photo_url: str = Field(min_length=1, max_length=1024)


class LobbyPlayerPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    membership_id: uuid.UUID
    player_card_id: uuid.UUID
    user_id: uuid.UUID
    username: str
    nickname: str
    lobby_photo_url: str | None = None
    photo_urls: list[str]
    game_role: str | None
    status: str | None
    joined_at: datetime


class GameLobbyPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    overlay_public_id: uuid.UUID
    max_players: int
    title: str
    host_user_id: uuid.UUID | None = None
    selected_overlay_design: str
    active_overlay_screen: str
    design_catalog: list[LobbyOverlayDesignOption]
    sheriff_check: list[str]
    best_move: list[str]
    imported_state: ImportedLobbyState | None = None
    created_at: datetime
    players: list[LobbyPlayerPublic]
