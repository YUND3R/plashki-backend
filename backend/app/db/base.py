from enum import Enum

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass



LOBBY_MAX_PLAYERS: int = 10


class Role(Enum):
    ADMIN = "admin"
    MODERATOR = "moderator"
    SPONSOR = "sponsor"
    USER = "user"


class Subscription(Enum):
    FREE = "free"
    STANDARD = "standard"
    PREMIUM = "premium"


class OverlayDesign(Enum):
    """Визуальная тема карточек overlay для OBS."""

    MASTERS_YUG25 = "masters-yug25"
    CLASSIC = "classic"
    PLUS = "plus"


class GameRole(Enum):
    """Роль в партии; задаётся и снимается API в любой фазе (лобби или идущая сессия)."""

    PEACEFUL = "peaceful"
    MAFIA = "mafia"
    DON = "don"  
    SHERIFF = "sheriff" 


class GameStatus(Enum):
    """Статус места/игрока в игровом лобби."""

    KILLED = "killed"
    VOTED = "voted"
    DELETED = "deleted"
    FOUL = "foul"
    BEST_MOVE = "best-move"
    PLAYER_SPEECH = "player-speech"
    PROTOCOL = "protocol"
    OPINION = "opinion"


class RatingWinnerSide(Enum):
    RED = "red"
    BLACK = "black"


class RatingGameSource(Enum):
    MANUAL = "manual"
    LOBBY_SYNC = "lobby_sync"