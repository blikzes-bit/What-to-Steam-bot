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


class SteamStoreClient:
    def __init__(self, http: httpx.AsyncClient, country: str, language: str) -> None:
        self.http = http
        self.country = country
        self.language = language

    async def get_offer(self, app_id: int) -> StoreOffer:
        try:
            response = await self.http.get(
                "https://store.steampowered.com/api/appdetails",
                params={"appids": app_id, "cc": self.country, "l": self.language},
            )
            response.raise_for_status()
            payload = response.json().get(str(app_id), {})
        except (httpx.HTTPError, ValueError) as exc:
            raise StoreApiError("Магазин Steam временно недоступен") from exc

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
        )
