from dataclasses import dataclass
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


class SteamClient:
    def __init__(self, api_key: str, http: httpx.AsyncClient) -> None:
        self.api_key = api_key
        self.http = http
        self.base_url = "https://api.steampowered.com"

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

    async def _get(self, path: str, params: dict[str, str | int]) -> dict:
        try:
            response = await self.http.get(f"{self.base_url}{path}", params=params)
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise SteamApiError("Steam API временно недоступен") from exc
