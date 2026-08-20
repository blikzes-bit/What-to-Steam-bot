import asyncio
from dataclasses import dataclass

import httpx


class StoreApiError(RuntimeError):
    pass


@dataclass(slots=True, frozen=True)
class StoreOffer:
    app_id: int
    name: str
    discount_percent: int
    initial_price: int | None
    final_price: int | None
    currency: str | None
    is_free: bool
    short_description: str
    genres: tuple[str, ...]
    release_date: str | None


@dataclass(slots=True, frozen=True)
class StoreCatalogItem:
    app_id: int
    name: str
    discount_percent: int
    initial_price: int | None
    final_price: int | None
    currency: str | None


@dataclass(slots=True, frozen=True)
class StoreCatalog:
    specials: tuple[StoreCatalogItem, ...]
    new_releases: tuple[StoreCatalogItem, ...]
    top_sellers: tuple[StoreCatalogItem, ...]


class SteamStoreClient:
    def __init__(self, http: httpx.AsyncClient, country: str, language: str) -> None:
        self.http = http
        self.country = country
        self.language = language
        self._request_slots = asyncio.Semaphore(5)

    async def get_offer(self, app_id: int) -> StoreOffer:
        response_data = await self._get_json(
            "https://store.steampowered.com/api/appdetails",
            {"appids": app_id, "cc": self.country, "l": self.language},
        )
        payload = response_data.get(str(app_id), {})

        if not payload.get("success") or not payload.get("data"):
            raise StoreApiError("Игра не найдена в магазине Steam")

        data = payload["data"]
        price = data.get("price_overview") or {}
        return StoreOffer(
            app_id=app_id,
            name=data.get("name", f"App {app_id}"),
            discount_percent=int(price.get("discount_percent", 0)),
            initial_price=price.get("initial"),
            final_price=price.get("final"),
            currency=price.get("currency"),
            is_free=bool(data.get("is_free", False)),
            short_description=data.get("short_description", ""),
            genres=tuple(item.get("description", "") for item in data.get("genres", [])),
            release_date=(data.get("release_date") or {}).get("date"),
        )

    async def get_featured_catalog(self) -> StoreCatalog:
        data = await self._get_json(
            "https://store.steampowered.com/api/featuredcategories",
            {"cc": self.country, "l": self.language},
        )
        return StoreCatalog(
            specials=self._parse_catalog_items(data.get("specials", {}).get("items", [])),
            new_releases=self._parse_catalog_items(data.get("new_releases", {}).get("items", [])),
            top_sellers=self._parse_catalog_items(data.get("top_sellers", {}).get("items", [])),
        )

    @staticmethod
    def _parse_catalog_items(items: list[dict]) -> tuple[StoreCatalogItem, ...]:
        parsed: list[StoreCatalogItem] = []
        for item in items:
            app_id = item.get("id")
            if not isinstance(app_id, int) or item.get("type", 0) != 0:
                continue
            parsed.append(
                StoreCatalogItem(
                    app_id=app_id,
                    name=item.get("name", f"App {app_id}"),
                    discount_percent=int(item.get("discount_percent", 0)),
                    initial_price=item.get("original_price"),
                    final_price=item.get("final_price"),
                    currency=item.get("currency"),
                )
            )
        return tuple(parsed)

    async def _get_json(self, url: str, params: dict[str, str | int]) -> dict:
        for attempt in range(3):
            try:
                async with self._request_slots:
                    response = await self.http.get(url, params=params)
                if response.status_code == 429 or response.status_code >= 500:
                    raise httpx.HTTPStatusError(
                        "Retryable Steam Store response",
                        request=response.request,
                        response=response,
                    )
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise ValueError("Unexpected Steam Store response")
                return payload
            except (httpx.TransportError, httpx.HTTPStatusError, ValueError) as exc:
                if attempt == 2 or (
                    isinstance(exc, httpx.HTTPStatusError)
                    and exc.response.status_code < 500
                    and exc.response.status_code != 429
                ):
                    raise StoreApiError("Магазин Steam временно недоступен") from exc
                await asyncio.sleep(0.5 * (2**attempt))
        raise StoreApiError("Магазин Steam временно недоступен")
