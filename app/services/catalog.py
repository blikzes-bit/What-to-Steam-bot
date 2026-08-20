from app.clients.store import StoreCatalog, StoreCatalogItem


def select_deals(catalog: StoreCatalog, threshold: int, count: int = 8) -> list[StoreCatalogItem]:
    unique: dict[int, StoreCatalogItem] = {}
    for item in catalog.specials:
        if item.discount_percent >= threshold:
            unique[item.app_id] = item
    return sorted(
        unique.values(),
        key=lambda item: (-item.discount_percent, item.final_price or 0, item.name.casefold()),
    )[:count]


def select_releases(catalog: StoreCatalog, count: int = 5) -> list[StoreCatalogItem]:
    top_ids = {item.app_id for item in catalog.top_sellers}
    indexed = list(enumerate(catalog.new_releases))
    indexed.sort(key=lambda pair: (pair[1].app_id not in top_ids, pair[0]))
    seen: set[int] = set()
    result: list[StoreCatalogItem] = []
    for _index, item in indexed:
        if item.app_id in seen:
            continue
        result.append(item)
        seen.add(item.app_id)
        if len(result) >= count:
            break
    return result
