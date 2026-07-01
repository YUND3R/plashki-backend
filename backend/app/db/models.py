import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, SmallInteger, String, Uuid, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import (
    LOBBY_MAX_PLAYERS,
    Base,
    GameRole,
    GameStatus,
    OverlayDesign,
    Role,
    Subscription,
)


class UserProfile(Base):
    __tablename__ = "user_profile"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    role: Mapped[Role] = mapped_column(
        Enum(Role, native_enum=False, values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        server_default=Role.USER.value,
    )
    
    subscription: Mapped[Subscription] = mapped_column(
        Enum(Subscription, native_enum=False, values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        server_default=Subscription.FREE.value,
    )


    username: Mapped[str] = mapped_column(String(55), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(55), unique=True, index=True, nullable=False)
    first_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        server_default=text("''"),
    )
    last_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        server_default=text("''"),
    )
    avatar_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    # В БД могла остаться колонка от старой схемы; NOT NULL — задаём при регистрации (часто = username).
    nickname: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    subscription_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    active_overlay_lobby_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    player_cards: Mapped[list["PlayerCard"]] = relationship(
        back_populates="owner",
        cascade="all, delete-orphan",
    )
    hosted_lobbies: Mapped[list["GameLobby"]] = relationship(back_populates="host")
    password_reset_tokens: Mapped[list["PasswordResetToken"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    email_verification_tokens: Mapped[list["EmailVerificationToken"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    feedback_messages: Mapped[list["FeedbackMessage"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    overlay_design_access: Mapped[list["UserOverlayDesignAccess"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )

    def is_subscription_active(self) -> bool:
        if self.subscription == Subscription.FREE:
            return True
        if self.subscription_until is None:
            return False
        end = self.subscription_until
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        return end > datetime.now(timezone.utc)


class PendingRegistration(Base):
    __tablename__ = "pending_registration"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    username: Mapped[str] = mapped_column(String(55), unique=True, index=True, nullable=False)
    email: Mapped[str] = mapped_column(String(55), unique=True, index=True, nullable=False)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    verification_tokens: Mapped[list["EmailVerificationToken"]] = relationship(
        back_populates="pending_registration",
        cascade="all, delete-orphan",
    )


class PlayerCard(Base):
    """Игровые данные без отдельного аккаунта у «персонажа».

    Создатель/владелец — user_profile.id в поле owner_user_id.
    """

    __tablename__ = "player_card"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("user_profile.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    nickname: Mapped[str] = mapped_column(String(255), nullable=False)
    club: Mapped[str | None] = mapped_column(String(255), nullable=True)
    gomafia_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    photo_urls: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    owner: Mapped["UserProfile"] = relationship(back_populates="player_cards")
    lobby_memberships: Mapped[list["LobbyMembership"]] = relationship(
        back_populates="player_card",
    )


class GameLobby(Base):
    """Игровое лобби на 10 мест (max_players). Роли висят на LobbyMembership.game_role.

    Пример классического набора на 10: 1 дон, 2 мафии, 1 шериф, 6 мирных —
    конкретные числа задаёшь в логике раздачи (сервисе), а в БД хранится роль каждого.
    """

    __tablename__ = "game_lobby"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    overlay_public_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        unique=True,
        index=True,
        nullable=False,
        default=uuid.uuid4,
    )
    max_players: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=LOBBY_MAX_PLAYERS,
        server_default=str(LOBBY_MAX_PLAYERS),
    )
    title: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
        server_default=text("'Лобби'"),
    )
    host_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("user_profile.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    selected_overlay_design: Mapped[OverlayDesign] = mapped_column(
        Enum(
            OverlayDesign,
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
        server_default=OverlayDesign.CLASSIC.value,
    )
    # Активный экран overlay для OBS (переключается кнопками в панели управления).
    active_overlay_screen: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        server_default=text("'lobby'"),
    )
    # Массив из 5 отметок проверки шерифа (формат задаёт клиент/overlay).
    sheriff_check: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
    )
    # Массив из 3 отметок best move (формат задаёт клиент/overlay).
    best_move: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
    )
    imported_source_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    imported_current_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    imported_variants: Mapped[list[dict]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    member_links: Mapped[list["LobbyMembership"]] = relationship(
        back_populates="lobby",
        cascade="all, delete-orphan",
    )
    host: Mapped["UserProfile | None"] = relationship(back_populates="hosted_lobbies")


class LobbyMembership(Base):
    """Место в лобби = карточка игрока (листочек). Добавить можно только свою карточку (owner = acting user)."""

    __tablename__ = "lobby_membership"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    lobby_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("game_lobby.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    player_card_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("player_card.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    # Порядок мест за столом (0 … max_players−1); меняется обменом мест хостом.
    seat_order: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        server_default="0",
        index=True,
    )
    # null — роль не задана; значение можно снять или выставить API в любой фазе (лобби / игра).
    game_role: Mapped[GameRole | None] = mapped_column(
        Enum(
            GameRole,
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=True,
    )
    # null — статус не задан; используется только в игровом лобби.
    status: Mapped[GameStatus | None] = mapped_column(
        Enum(
            GameStatus,
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=True,
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # URL снимка только для отображения в лобби (должен входить в photo_urls карточки).
    lobby_photo_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    lobby: Mapped["GameLobby"] = relationship(back_populates="member_links")
    player_card: Mapped["PlayerCard"] = relationship(back_populates="lobby_memberships")


class PasswordResetToken(Base):
    __tablename__ = "password_reset_token"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("user_profile.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    token_hash: Mapped[str | None] = mapped_column(
        String(64),
        unique=True,
        index=True,
        nullable=True,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    user: Mapped["UserProfile"] = relationship(back_populates="password_reset_tokens")


class EmailVerificationToken(Base):
    __tablename__ = "email_verification_token"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("user_profile.id", ondelete="CASCADE"),
        index=True,
        nullable=True,
    )
    pending_registration_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("pending_registration.id", ondelete="CASCADE"),
        index=True,
        nullable=True,
    )
    token_hash: Mapped[str | None] = mapped_column(
        String(64),
        unique=True,
        index=True,
        nullable=True,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    user: Mapped["UserProfile | None"] = relationship(back_populates="email_verification_tokens")
    pending_registration: Mapped["PendingRegistration | None"] = relationship(
        back_populates="verification_tokens"
    )


class FeedbackMessage(Base):
    __tablename__ = "feedback_message"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("user_profile.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    message: Mapped[str] = mapped_column(String(4000), nullable=False)
    page_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    user: Mapped["UserProfile"] = relationship(back_populates="feedback_messages")


class UserOverlayDesignAccess(Base):
    """Аренда плашки (overlay design) на 48 часов после оплаты."""

    __tablename__ = "user_overlay_design_access"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("user_profile.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    design_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped["UserProfile"] = relationship(back_populates="overlay_design_access")

