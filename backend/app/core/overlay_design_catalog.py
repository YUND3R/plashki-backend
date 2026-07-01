from dataclasses import dataclass

from app.db.base import OverlayDesign

RENTAL_HOURS = 48


@dataclass(frozen=True, slots=True)
class OverlayDesignCatalogEntry:
    code: OverlayDesign
    title: str
    price_rub: int
    rental_hours: int
    animations_supported: bool


OVERLAY_DESIGN_CATALOG: dict[OverlayDesign, OverlayDesignCatalogEntry] = {
    OverlayDesign.PLUS: OverlayDesignCatalogEntry(
        code=OverlayDesign.PLUS,
        title="Plus",
        price_rub=300,
        rental_hours=RENTAL_HOURS,
        animations_supported=True,
    ),
    OverlayDesign.CLASSIC: OverlayDesignCatalogEntry(
        code=OverlayDesign.CLASSIC,
        title="Classic",
        price_rub=500,
        rental_hours=RENTAL_HOURS,
        animations_supported=True,
    ),
    OverlayDesign.MASTERS_YUG25: OverlayDesignCatalogEntry(
        code=OverlayDesign.MASTERS_YUG25,
        title="Мастерс ЮГ25",
        price_rub=900,
        rental_hours=RENTAL_HOURS,
        animations_supported=True,
    ),
}


def get_catalog_entry(design: OverlayDesign) -> OverlayDesignCatalogEntry | None:
    return OVERLAY_DESIGN_CATALOG.get(design)
