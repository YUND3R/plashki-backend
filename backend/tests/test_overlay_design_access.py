from datetime import UTC, datetime, timedelta

from app.core.overlay_design_catalog import OVERLAY_DESIGN_CATALOG
from app.db.base import OverlayDesign, Role
from app.services.overlay_design_access import (
    compute_rental_expires_at,
    role_has_unlimited_design_access,
)


def test_role_has_unlimited_design_access_for_admin_and_sponsor() -> None:
    assert role_has_unlimited_design_access(Role.ADMIN) is True
    assert role_has_unlimited_design_access(Role.SPONSOR) is True
    assert role_has_unlimited_design_access(Role.USER) is False
    assert role_has_unlimited_design_access(Role.MODERATOR) is False


def test_overlay_design_catalog_prices() -> None:
    assert OVERLAY_DESIGN_CATALOG[OverlayDesign.PLUS].price_rub == 300
    assert OVERLAY_DESIGN_CATALOG[OverlayDesign.CLASSIC].price_rub == 500
    assert OVERLAY_DESIGN_CATALOG[OverlayDesign.MASTERS_YUG25].price_rub == 900
    for entry in OVERLAY_DESIGN_CATALOG.values():
        assert entry.rental_hours == 48


def test_compute_rental_expires_from_now() -> None:
    now = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    expires = compute_rental_expires_at(rental_hours=48, now=now, current_expires_at=None)
    assert expires == now + timedelta(hours=48)


def test_compute_rental_extends_active_access() -> None:
    now = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    current = datetime(2026, 6, 2, 12, 0, tzinfo=UTC)
    expires = compute_rental_expires_at(rental_hours=48, now=now, current_expires_at=current)
    assert expires == current + timedelta(hours=48)


def test_compute_rental_starts_fresh_after_expiry() -> None:
    now = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    expired = datetime(2026, 5, 31, 12, 0, tzinfo=UTC)
    expires = compute_rental_expires_at(rental_hours=48, now=now, current_expires_at=expired)
    assert expires == now + timedelta(hours=48)
