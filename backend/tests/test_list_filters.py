from app.schemas.list_filters import (
    AdminUserListFilters,
    LobbyListFilters,
    PlayerCardListFilters,
)
from app.services.list_query import ilike_pattern


def test_ilike_pattern_trims_whitespace() -> None:
    assert ilike_pattern("  test  ") == "%test%"


def test_lobby_list_filter_defaults() -> None:
    filters = LobbyListFilters()
    assert filters.source == "all"


def test_player_card_list_filter_defaults() -> None:
    filters = PlayerCardListFilters()
    assert filters.has_photos is None
    assert filters.sort_by == "created_at"
    assert filters.sort_order == "asc"


def test_admin_user_list_filter_defaults() -> None:
    filters = AdminUserListFilters()
    assert filters.role is None
    assert filters.subscription is None
    assert filters.sort_by == "created_at"
