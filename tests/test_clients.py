import httpx
import pytest
import respx

from app.clients.steam import SteamApiError, SteamClient
from app.clients.store import SteamStoreClient


@pytest.mark.asyncio
async def test_resolve_numeric_profile_without_request() -> None:
    async with httpx.AsyncClient() as http:
        client = SteamClient("test-key", http)
        assert await client.resolve_profile_input("76561198000000000") == 76561198000000000


@pytest.mark.asyncio
@respx.mock
async def test_resolve_vanity_profile() -> None:
    respx.get("https://api.steampowered.com/ISteamUser/ResolveVanityURL/v1/").mock(
        return_value=httpx.Response(
            200, json={"response": {"success": 1, "steamid": "76561198000000000"}}
        )
    )
    async with httpx.AsyncClient() as http:
        client = SteamClient("test-key", http)
        result = await client.resolve_profile_input("https://steamcommunity.com/id/example/")
    assert result == 76561198000000000


@pytest.mark.asyncio
async def test_invalid_profile_input() -> None:
    async with httpx.AsyncClient() as http:
        client = SteamClient("test-key", http)
        with pytest.raises(SteamApiError):
            await client.resolve_profile_input("not-a-steam-profile")


@pytest.mark.asyncio
@respx.mock
async def test_store_offer_parsing() -> None:
    respx.get("https://store.steampowered.com/api/appdetails").mock(
        return_value=httpx.Response(
            200,
            json={
                "730": {
                    "success": True,
                    "data": {
                        "name": "Counter-Strike 2",
                        "is_free": True,
                        "price_overview": {
                            "discount_percent": 50,
                            "initial": 10000,
                            "final": 5000,
                            "currency": "UAH",
                        },
                    },
                }
            },
        )
    )
    async with httpx.AsyncClient() as http:
        offer = await SteamStoreClient(http, "UA", "russian").get_offer(730)

    assert offer.name == "Counter-Strike 2"
    assert offer.discount_percent == 50
    assert offer.final_price == 5000
