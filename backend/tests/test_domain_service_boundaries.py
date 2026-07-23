from types import SimpleNamespace
import uuid

import pytest

from app.broadcast.application.overlay import (
    get_overlay_design_catalog_for_user,
    set_lobby_overlay_design,
)
from app.commerce.application.contracts import OverlayDesignOption
from app.db.base import OverlayDesign
from app.db.models import GameLobby, UserProfile
from app.sessions.application.memberships import add_card_to_lobby
from app.sessions.application.roster import RosterCard


class FakeDesignAccess:
    def __init__(self, *, allowed: bool):
        self.allowed = allowed
        self.requested_users: list[uuid.UUID | None] = []

    async def options_for_user(self, user_id):
        self.requested_users.append(user_id)
        return [
            OverlayDesignOption(
                code=OverlayDesign.CLASSIC,
                title="Classic",
                price_rub=500,
                rental_hours=48,
                animations_supported=False,
                selectable=self.allowed,
            )
        ]

    async def can_use(self, _user_id, _design):
        return self.allowed

    async def host_has_access(self, _host_user_id, _design):
        return self.allowed


class FakeGetSession:
    def __init__(self, objects):
        self.objects = objects

    async def get(self, model, ident):
        return self.objects.get((model, ident))


@pytest.mark.asyncio
async def test_broadcast_catalog_uses_commerce_port_contract() -> None:
    user_id = uuid.uuid4()
    access = FakeDesignAccess(allowed=True)
    session = FakeGetSession({(UserProfile, user_id): SimpleNamespace(id=user_id)})

    result = await get_overlay_design_catalog_for_user(session, user_id, access)

    assert result is not None
    assert result.options[0].code is OverlayDesign.CLASSIC
    assert result.options[0].selectable is True
    assert access.requested_users == [user_id]


@pytest.mark.asyncio
async def test_broadcast_design_selection_is_denied_by_commerce_port() -> None:
    user_id = uuid.uuid4()
    lobby_id = uuid.uuid4()
    lobby = SimpleNamespace(id=lobby_id, host_user_id=user_id)
    session = FakeGetSession(
        {
            (GameLobby, lobby_id): lobby,
            (UserProfile, user_id): SimpleNamespace(id=user_id),
        }
    )

    error, result = await set_lobby_overlay_design(
        session,
        lobby_id,
        OverlayDesign.CLASSIC,
        user_id,
        FakeDesignAccess(allowed=False),
    )

    assert error == "design_access_required"
    assert result is None


class FakeRoster:
    def __init__(self, card: RosterCard):
        self.card = card

    async def get_card(self, _card_id):
        return self.card


class FakeScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class FakeMembershipSession:
    def __init__(self, lobby):
        self.lobby = lobby

    async def execute(self, _statement):
        return FakeScalarResult(self.lobby)


@pytest.mark.asyncio
async def test_sessions_membership_checks_owner_through_roster_port() -> None:
    owner_id = uuid.uuid4()
    acting_user_id = uuid.uuid4()
    card_id = uuid.uuid4()
    lobby_id = uuid.uuid4()
    roster = FakeRoster(
        RosterCard(
            id=card_id,
            owner_user_id=owner_id,
            photo_urls=frozenset(),
        )
    )
    session = FakeMembershipSession(
        SimpleNamespace(id=lobby_id, member_links=[], max_players=10)
    )

    error, result = await add_card_to_lobby(
        session,
        lobby_id,
        card_id,
        acting_user_id,
        roster=roster,
    )

    assert error == "not_card_owner"
    assert result is None
