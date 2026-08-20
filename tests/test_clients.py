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
                        "short_description": "Competitive shooter",
                        "genres": [{"description": "Action"}],
                        "release_date": {"date": "21 Aug, 2012"},
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
    assert offer.short_description == "Competitive shooter"
    assert offer.genres == ("Action",)


@pytest.mark.asyncio
@respx.mock
async def test_recently_played_parsing() -> None:
    respx.get("https://api.steampowered.com/IPlayerService/GetRecentlyPlayedGames/v1/").mock(
        return_value=httpx.Response(
            200,
            json={
                "response": {
                    "games": [
                        {
                            "appid": 730,
                            "name": "Counter-Strike 2",
                            "playtime_forever": 600,
                            "playtime_2weeks": 120,
                        }
                    ]
                }
            },
        )
    )
    async with httpx.AsyncClient() as http:
        games = await SteamClient("test-key", http).get_recently_played(76561198000000000)

    assert games[0].app_id == 730
    assert games[0].playtime_two_weeks == 120


@pytest.mark.asyncio
@respx.mock
async def test_achievements_parsing() -> None:
    respx.get("https://api.steampowered.com/ISteamUserStats/GetPlayerAchievements/v1/").mock(
        return_value=httpx.Response(
            200,
            json={
                "playerstats": {
                    "success": True,
                    "achievements": [
                        {
                            "apiname": "FIRST_WIN",
                            "name": "First Win",
                            "description": "Win once",
                            "achieved": 1,
                            "unlocktime": 123,
                        }
                    ],
                }
            },
        )
    )
    async with httpx.AsyncClient() as http:
        achievements = await SteamClient("test-key", http).get_achievements(76561198000000000, 730)

    assert achievements[0].achieved is True
    assert achievements[0].name == "First Win"


@pytest.mark.asyncio
@respx.mock
async def test_current_players_and_bans_parsing() -> None:
    respx.get("https://api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers/v1/").mock(
        return_value=httpx.Response(200, json={"response": {"result": 1, "player_count": 42}})
    )
    respx.get("https://api.steampowered.com/ISteamUser/GetPlayerBans/v1/").mock(
        return_value=httpx.Response(
            200,
            json={
                "players": [
                    {
                        "VACBanned": False,
                        "NumberOfVACBans": 0,
                        "NumberOfGameBans": 1,
                        "CommunityBanned": False,
                        "EconomyBan": "none",
                        "DaysSinceLastBan": 50,
                    }
                ]
            },
        )
    )
    async with httpx.AsyncClient() as http:
        client = SteamClient("test-key", http)
        players = await client.get_current_players(730)
        bans = await client.get_player_bans(76561198000000000)

    assert players == 42
    assert bans.game_bans == 1
    assert bans.vac_banned is False


@pytest.mark.asyncio
@respx.mock
async def test_steam_level_parsing() -> None:
    respx.get("https://api.steampowered.com/IPlayerService/GetSteamLevel/v1/").mock(
        return_value=httpx.Response(200, json={"response": {"player_level": 42}})
    )
    async with httpx.AsyncClient() as http:
        level = await SteamClient("test-key", http).get_steam_level(76561198000000000)

    assert level == 42
