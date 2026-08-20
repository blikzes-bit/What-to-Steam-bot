import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlparse

import httpx


class SteamApiError(RuntimeError):
    pass


@dataclass(slots=True, frozen=True)
class SteamProfile:
    steam_id: int
    name: str
    profile_url: str
    avatar_url: str | None
    visibility: int
    persona_state: int
    game_name: str | None


@dataclass(slots=True, frozen=True)
class OwnedGame:
    app_id: int
    name: str
    icon_hash: str | None
    playtime_forever: int
    playtime_two_weeks: int | None


@dataclass(slots=True, frozen=True)
class Achievement:
    api_name: str
    name: str
    description: str
    achieved: bool
    unlock_time: int


@dataclass(slots=True, frozen=True)
class PlayerBans:
    vac_banned: bool
    vac_bans: int
    game_bans: int
    community_banned: bool
    economy_ban: str
    days_since_last_ban: int


@dataclass(slots=True, frozen=True)
class NewsItem:
    title: str
    url: str
    author: str
    published_at: datetime


class SteamClient:
    def __init__(self, api_key: str, http: httpx.AsyncClient) -> None:
        self.api_key = api_key
        self.http = http
        self.base_url = "https://api.steampowered.com"
        self._request_slots = asyncio.Semaphore(5)

    async def resolve_profile_input(self, value: str) -> int:
        value = value.strip().rstrip("/")
        if value.isdigit():
            return int(value)

        parsed = urlparse(value if "://" in value else f"https://{value}")
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) >= 2 and parts[-2] == "profiles" and parts[-1].isdigit():
            return int(parts[-1])
        if len(parts) >= 2 and parts[-2] == "id":
            return await self.resolve_vanity(parts[-1])
        raise SteamApiError("Не удалось распознать SteamID или ссылку на профиль")

    async def resolve_vanity(self, vanity: str) -> int:
        data = await self._get(
            "/ISteamUser/ResolveVanityURL/v1/",
            {"key": self.api_key, "vanityurl": vanity},
        )
        response = data.get("response", {})
        if response.get("success") != 1 or not response.get("steamid"):
            raise SteamApiError("Steam-профиль не найден")
        return int(response["steamid"])

    async def get_profiles(self, steam_ids: list[int]) -> list[SteamProfile]:
        if not steam_ids:
            return []
        profiles: list[SteamProfile] = []
        for offset in range(0, len(steam_ids), 100):
            batch = steam_ids[offset : offset + 100]
            data = await self._get(
                "/ISteamUser/GetPlayerSummaries/v2/",
                {"key": self.api_key, "steamids": ",".join(map(str, batch))},
            )
            for player in data.get("response", {}).get("players", []):
                profiles.append(
                    SteamProfile(
                        steam_id=int(player["steamid"]),
                        name=player.get("personaname", "Unknown"),
                        profile_url=player.get("profileurl", ""),
                        avatar_url=player.get("avatarfull"),
                        visibility=int(player.get("communityvisibilitystate", 0)),
                        persona_state=int(player.get("personastate", 0)),
                        game_name=player.get("gameextrainfo"),
                    )
                )
        return profiles

    async def get_profile(self, steam_id: int) -> SteamProfile:
        profiles = await self.get_profiles([steam_id])
        if not profiles:
            raise SteamApiError("Steam-профиль не найден")
        return profiles[0]

    async def get_owned_games(self, steam_id: int) -> list[OwnedGame]:
        data = await self._get(
            "/IPlayerService/GetOwnedGames/v1/",
            {
                "key": self.api_key,
                "steamid": steam_id,
                "include_appinfo": "true",
                "include_played_free_games": "true",
            },
        )
        response = data.get("response", {})
        if "games" not in response:
            raise SteamApiError("Библиотека закрыта или недоступна")
        return [
            OwnedGame(
                app_id=int(game["appid"]),
                name=game.get("name", f"App {game['appid']}"),
                icon_hash=game.get("img_icon_url"),
                playtime_forever=int(game.get("playtime_forever", 0)),
                playtime_two_weeks=game.get("playtime_2weeks"),
            )
            for game in response["games"]
        ]

    async def get_recently_played(self, steam_id: int, count: int = 10) -> list[OwnedGame]:
        data = await self._get(
            "/IPlayerService/GetRecentlyPlayedGames/v1/",
            {"key": self.api_key, "steamid": steam_id, "count": count},
        )
        return [
            OwnedGame(
                app_id=int(game["appid"]),
                name=game.get("name", f"App {game['appid']}"),
                icon_hash=game.get("img_icon_url"),
                playtime_forever=int(game.get("playtime_forever", 0)),
                playtime_two_weeks=game.get("playtime_2weeks"),
            )
            for game in data.get("response", {}).get("games", [])
        ]

    async def get_achievements(self, steam_id: int, app_id: int) -> list[Achievement]:
        data = await self._get(
            "/ISteamUserStats/GetPlayerAchievements/v1/",
            {
                "key": self.api_key,
                "steamid": steam_id,
                "appid": app_id,
                "l": "russian",
            },
        )
        player_stats = data.get("playerstats", {})
        if player_stats.get("success") is False:
            raise SteamApiError("Достижения игры закрыты или недоступны")
        return [
            Achievement(
                api_name=item.get("apiname", ""),
                name=item.get("name") or item.get("apiname", "Неизвестное достижение"),
                description=item.get("description") or "Без описания",
                achieved=bool(item.get("achieved")),
                unlock_time=int(item.get("unlocktime", 0)),
            )
            for item in player_stats.get("achievements", [])
        ]

    async def get_current_players(self, app_id: int) -> int:
        data = await self._get(
            "/ISteamUserStats/GetNumberOfCurrentPlayers/v1/",
            {"appid": app_id},
        )
        response = data.get("response", {})
        if response.get("result") != 1:
            raise SteamApiError("Онлайн игры недоступен")
        return int(response.get("player_count", 0))

    async def get_steam_level(self, steam_id: int) -> int:
        data = await self._get(
            "/IPlayerService/GetSteamLevel/v1/",
            {"key": self.api_key, "steamid": steam_id},
        )
        response = data.get("response", {})
        if "player_level" not in response:
            raise SteamApiError("Уровень Steam недоступен")
        return int(response["player_level"])

    async def get_player_bans(self, steam_id: int) -> PlayerBans:
        data = await self._get(
            "/ISteamUser/GetPlayerBans/v1/",
            {"key": self.api_key, "steamids": str(steam_id)},
        )
        players = data.get("players", [])
        if not players:
            raise SteamApiError("Информация о блокировках недоступна")
        player = players[0]
        return PlayerBans(
            vac_banned=bool(player.get("VACBanned")),
            vac_bans=int(player.get("NumberOfVACBans", 0)),
            game_bans=int(player.get("NumberOfGameBans", 0)),
            community_banned=bool(player.get("CommunityBanned")),
            economy_ban=player.get("EconomyBan", "none"),
            days_since_last_ban=int(player.get("DaysSinceLastBan", 0)),
        )

    async def get_news(self, app_id: int, count: int = 3) -> list[NewsItem]:
        data = await self._get(
            "/ISteamNews/GetNewsForApp/v2/",
            {"appid": app_id, "count": count, "maxlength": 300},
        )
        return [
            NewsItem(
                title=item.get("title", "Без названия"),
                url=item.get("url", ""),
                author=item.get("author", "Steam"),
                published_at=datetime.fromtimestamp(int(item.get("date", 0)), tz=UTC),
            )
            for item in data.get("appnews", {}).get("newsitems", [])
        ]

    async def _get(self, path: str, params: dict[str, str | int]) -> dict:
        for attempt in range(3):
            try:
                async with self._request_slots:
                    response = await self.http.get(f"{self.base_url}{path}", params=params)
                if response.status_code == 429 or response.status_code >= 500:
                    raise httpx.HTTPStatusError(
                        "Retryable Steam API response",
                        request=response.request,
                        response=response,
                    )
                response.raise_for_status()
                return response.json()
            except (httpx.TransportError, httpx.HTTPStatusError, ValueError) as exc:
                if attempt == 2 or (
                    isinstance(exc, httpx.HTTPStatusError)
                    and exc.response.status_code < 500
                    and exc.response.status_code != 429
                ):
                    raise SteamApiError("Steam API временно недоступен") from exc
                await asyncio.sleep(0.5 * (2**attempt))
        raise SteamApiError("Steam API временно недоступен")
