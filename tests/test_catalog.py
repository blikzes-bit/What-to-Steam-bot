from app.clients.store import StoreCatalog, StoreCatalogItem
from app.services.catalog import select_deals, select_releases


def item(app_id: int, discount: int = 0, price: int = 1000) -> StoreCatalogItem:
    return StoreCatalogItem(
        app_id=app_id,
        name=f"Game {app_id}",
        discount_percent=discount,
        initial_price=price * 2,
        final_price=price,
        currency="UAH",
    )


def test_select_deals_filters_sorts_and_deduplicates() -> None:
    catalog = StoreCatalog(
        specials=(item(1, 50), item(2, 75), item(1, 50)),
        new_releases=(),
        top_sellers=(),
    )

    assert [deal.app_id for deal in select_deals(catalog, 50)] == [2, 1]


def test_select_releases_prioritizes_top_sellers() -> None:
    catalog = StoreCatalog(
        specials=(),
        new_releases=(item(1), item(2), item(3)),
        top_sellers=(item(2),),
    )

    assert [release.app_id for release in select_releases(catalog)] == [2, 1, 3]
