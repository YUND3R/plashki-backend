import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.db.base import OverlayDesign, Role, Subscription
from app.db.models import (
    CommerceUserSubscription,
    GameLobby,
    LobbyOverlayState,
    UserProfile,
)
from app.schemas.auth import AdminRegisteredUser


def test_user_public_attributes_are_backed_by_owned_rows() -> None:
    until = datetime.now(UTC) + timedelta(days=1)
    lobby_id = uuid.uuid4()
    user = UserProfile(
        id=uuid.uuid4(),
        username="normalized",
        email="normalized@example.test",
        first_name="Norm",
        last_name="User",
        nickname="normalized",
        hashed_password="hash",
        role=Role.USER,
        created_at=datetime.now(UTC),
        subscription=Subscription.PREMIUM,
        subscription_until=until,
        active_overlay_lobby_id=lobby_id,
    )

    assert user.subscription is Subscription.PREMIUM
    assert user.subscription_until == until
    assert user.active_overlay_lobby_id == lobby_id
    assert user.commerce_subscription.subscription is Subscription.PREMIUM
    assert user.broadcast_settings.active_overlay_lobby_id == lobby_id

    payload = AdminRegisteredUser.model_validate(user)
    assert payload.subscription is Subscription.PREMIUM


def test_lobby_public_attributes_are_backed_by_overlay_state() -> None:
    public_id = uuid.uuid4()
    lobby = GameLobby(
        overlay_public_id=public_id,
        selected_overlay_design=OverlayDesign.PLUS,
        active_overlay_screen="roles",
        show_victory_scores=True,
        sheriff_check=["1"],
        best_move=["2"],
    )

    assert lobby.overlay_public_id == public_id
    assert lobby.selected_overlay_design is OverlayDesign.PLUS
    assert lobby.active_overlay_screen == "roles"
    assert lobby.show_victory_scores is True
    assert lobby.sheriff_check == ["1"]
    assert lobby.best_move == ["2"]
    assert lobby.overlay_state.overlay_public_id == public_id

    lobby.active_overlay_screen = "victory"
    assert lobby.overlay_state.active_overlay_screen == "victory"


def test_owned_field_queries_target_normalized_tables() -> None:
    dialect = postgresql.dialect()
    subscription_sql = str(
        select(UserProfile.id)
        .join(UserProfile.commerce_subscription)
        .where(CommerceUserSubscription.subscription == Subscription.PREMIUM)
        .compile(dialect=dialect)
    )
    overlay_sql = str(
        select(GameLobby.id)
        .join(GameLobby.overlay_state)
        .where(LobbyOverlayState.overlay_public_id == uuid.uuid4())
        .compile(dialect=dialect)
    )

    assert "commerce_user_subscription" in subscription_sql
    assert "lobby_overlay_state" in overlay_sql


def test_legacy_columns_are_absent_from_parent_tables() -> None:
    assert {
        "subscription",
        "subscription_until",
        "active_overlay_lobby_id",
    }.isdisjoint(UserProfile.__table__.columns.keys())
    assert {
        "overlay_public_id",
        "selected_overlay_design",
        "active_overlay_screen",
        "show_victory_scores",
        "sheriff_check",
        "best_move",
    }.isdisjoint(GameLobby.__table__.columns.keys())
