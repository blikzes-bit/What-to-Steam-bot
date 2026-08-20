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


class SteamStoreClient:
    def __init__(self, http: httpx.AsyncClient, country: str, language: str) -> None:
        self.http = http
        self.country = country
        self.language = language
        self._request_slots = asyncio.Semaphore(5)

    async def get_offer(self, app_id: int) -> StoreOffer:
        payload: dict = {}
        for attempt in range(3):
            try:
                async with self._request_slots:
                    response = await self.http.get(
                        "https://store.steampowered.com/api/appdetails",
                        params={"appids": app_id, "cc": self.country, "l": self.language},
                    )
                if response.status_code == 429 or response.status_code >= 500:
                    raise httpx.HTTPStatusError(
                        "Retryable Steam Store response",
                        request=response.request,
                        response=response,
                    )
                response.raise_for_status()
                payload = response.json().get(str(app_id), {})
                break
            except (httpx.TransportError, httpx.HTTPStatusError, ValueError) as exc:
                if attempt == 2 or (
                    isinstance(exc, httpx.HTTPStatusError)
                    and exc.response.status_code < 500
                    and exc.response.status_code != 429
                ):
                    raise StoreApiError("Магазин Steam временно недоступен") from exc
                await asyncio.sleep(0.5 * (2**attempt))

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
