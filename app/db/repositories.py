from dataclasses import dataclass
from datetime import UTC, datetime

from aiogram.types import Chat as TelegramChat
from aiogram.types import User as TelegramUser
from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.steam import OwnedGame, SteamProfile
from app.db.models import (
    Chat,
    ChatMember,
    DigestSubscription,
    Game,
    Lobby,
    LobbyCandidate,
    LobbyMember,
    LobbyVote,
    SteamAccount,
    User,
    UserGame,
    WatchedGame,
)


@dataclass(slots=True, frozen=True)
class CommonGame:
    app_id: int
    name: str
    total_playtime: int


@dataclass(slots=True, frozen=True)
class LibraryStats:
    total_games: int
    total_minutes: int
    unplayed_games: int
    recent_minutes: int


async def ensure_user(session: AsyncSession, telegram_user: TelegramUser) -> User:
    statement = (
        pg_insert(User)
        .values(
            telegram_id=telegram_user.id,
            username=telegram_user.username,
            first_name=telegram_user.first_name,
        )
        .on_conflict_do_update(
            index_elements=[User.telegram_id],
            set_={
                "username": telegram_user.username,
                "first_name": telegram_user.first_name,
                "updated_at": func.now(),
            },
        )
        .returning(User)
    )
    return (await session.execute(statement)).scalar_one()


async def ensure_chat(session: AsyncSession, telegram_chat: TelegramChat) -> Chat:
    title = telegram_chat.title or telegram_chat.full_name or str(telegram_chat.id)
    statement = (
        pg_insert(Chat)
        .values(telegram_id=telegram_chat.id, title=title)
        .on_conflict_do_update(
            index_elements=[Chat.telegram_id],
            set_={"title": title, "updated_at": func.now()},
        )
        .returning(Chat)
    )
    return (await session.execute(statement)).scalar_one()


async def activate_chat_member(session: AsyncSession, chat_id: int, user_id: int) -> None:
    statement = (
        pg_insert(ChatMember)
        .values(chat_id=chat_id, user_id=user_id, active=True)
        .on_conflict_do_update(
            index_elements=[ChatMember.chat_id, ChatMember.user_id],
            set_={"active": True},
        )
    )
    await session.execute(statement)


async def get_steam_account(session: AsyncSession, user_id: int) -> SteamAccount | None:
    return await session.scalar(select(SteamAccount).where(SteamAccount.user_id == user_id))


async def link_steam_account(
    session: AsyncSession, user_id: int, profile: SteamProfile
) -> SteamAccount:
    owner = await session.scalar(
        select(SteamAccount).where(
            SteamAccount.steam_id == profile.steam_id,
            SteamAccount.user_id != user_id,
        )
    )
    if owner:
        raise ValueError("Этот Steam-профиль уже привязан к другому пользователю")

    statement = (
        pg_insert(SteamAccount)
        .values(
            user_id=user_id,
            steam_id=profile.steam_id,
            display_name=profile.name,
            profile_url=profile.profile_url,
            avatar_url=profile.avatar_url,
        )
        .on_conflict_do_update(
            index_elements=[SteamAccount.user_id],
            set_={
                "steam_id": profile.steam_id,
                "display_name": profile.name,
                "profile_url": profile.profile_url,
                "avatar_url": profile.avatar_url,
                "linked_at": func.now(),
            },
        )
        .returning(SteamAccount)
    )
    return (await session.execute(statement)).scalar_one()


async def sync_user_games(session: AsyncSession, user_id: int, games: list[OwnedGame]) -> None:
    now = datetime.now(UTC)
    app_ids = [game.app_id for game in games]
    if games:
        game_values = [
            {"app_id": game.app_id, "name": game.name, "icon_hash": game.icon_hash}
            for game in games
        ]
        game_statement = pg_insert(Game).values(game_values)
        await session.execute(
            game_statement.on_conflict_do_update(
                index_elements=[Game.app_id],
                set_={
                    "name": game_statement.excluded.name,
                    "icon_hash": game_statement.excluded.icon_hash,
                    "updated_at": func.now(),
                },
            )
        )

        owned_values = [
            {
                "user_id": user_id,
                "app_id": game.app_id,
                "playtime_forever": game.playtime_forever,
                "playtime_two_weeks": game.playtime_two_weeks,
                "synced_at": now,
            }
            for game in games
        ]
        owned_statement = pg_insert(UserGame).values(owned_values)
        await session.execute(
            owned_statement.on_conflict_do_update(
                index_elements=[UserGame.user_id, UserGame.app_id],
                set_={
                    "playtime_forever": owned_statement.excluded.playtime_forever,
                    "playtime_two_weeks": owned_statement.excluded.playtime_two_weeks,
                    "synced_at": now,
                },
            )
        )

    stale = delete(UserGame).where(UserGame.user_id == user_id)
    if app_ids:
        stale = stale.where(UserGame.app_id.not_in(app_ids))
    await session.execute(stale)
    await session.execute(
        update(SteamAccount).where(SteamAccount.user_id == user_id).values(last_synced_at=now)
    )


async def get_chat_linked_users(
    session: AsyncSession, chat_id: int
) -> list[tuple[User, SteamAccount]]:
    rows = await session.execute(
        select(User, SteamAccount)
        .join(ChatMember, ChatMember.user_id == User.id)
        .join(SteamAccount, SteamAccount.user_id == User.id)
        .where(ChatMember.chat_id == chat_id, ChatMember.active.is_(True))
        .order_by(User.first_name)
    )
    return list(rows.tuples())


async def get_common_games(session: AsyncSession, user_ids: list[int]) -> list[CommonGame]:
    if not user_ids:
        return []
    rows = await session.execute(
        select(
            Game.app_id,
            Game.name,
            func.sum(UserGame.playtime_forever).label("total_playtime"),
        )
        .join(UserGame, UserGame.app_id == Game.app_id)
        .where(UserGame.user_id.in_(user_ids))
        .group_by(Game.app_id, Game.name)
        .having(func.count(func.distinct(UserGame.user_id)) == len(set(user_ids)))
        .order_by(Game.name)
    )
    return [
        CommonGame(app_id=row.app_id, name=row.name, total_playtime=int(row.total_playtime or 0))
        for row in rows
    ]


async def get_chat_game_ownership(
    session: AsyncSession, chat_id: int, app_id: int
) -> list[tuple[User, bool]]:
    rows = await session.execute(
        select(User, UserGame.app_id)
        .join(ChatMember, ChatMember.user_id == User.id)
        .join(SteamAccount, SteamAccount.user_id == User.id)
        .outerjoin(
            UserGame,
            (UserGame.user_id == User.id) & (UserGame.app_id == app_id),
        )
        .where(ChatMember.chat_id == chat_id, ChatMember.active.is_(True))
        .order_by(User.first_name)
    )
    return [(user, owned_app_id is not None) for user, owned_app_id in rows]


async def get_user_backlog(session: AsyncSession, user_id: int) -> list[CommonGame]:
    rows = await session.execute(
        select(Game.app_id, Game.name, UserGame.playtime_forever)
        .join(UserGame, UserGame.app_id == Game.app_id)
        .where(UserGame.user_id == user_id, UserGame.playtime_forever == 0)
        .order_by(Game.name)
    )
    return [
        CommonGame(app_id=row.app_id, name=row.name, total_playtime=row.playtime_forever)
        for row in rows
    ]


async def get_user_game_ids(session: AsyncSession, user_id: int) -> set[int]:
    return set(
        (await session.scalars(select(UserGame.app_id).where(UserGame.user_id == user_id))).all()
    )


async def get_library_stats(session: AsyncSession, user_id: int) -> LibraryStats:
    row = (
        await session.execute(
            select(
                func.count(UserGame.app_id),
                func.coalesce(func.sum(UserGame.playtime_forever), 0),
                func.count(UserGame.app_id).filter(UserGame.playtime_forever == 0),
                func.coalesce(func.sum(UserGame.playtime_two_weeks), 0),
            ).where(UserGame.user_id == user_id)
        )
    ).one()
    return LibraryStats(
        total_games=int(row[0]),
        total_minutes=int(row[1]),
        unplayed_games=int(row[2]),
        recent_minutes=int(row[3]),
    )


async def unlink_steam_account(session: AsyncSession, user_id: int) -> bool:
    account_id = await session.scalar(
        select(SteamAccount.id).where(SteamAccount.user_id == user_id)
    )
    if account_id is None:
        return False
    await session.execute(delete(UserGame).where(UserGame.user_id == user_id))
    await session.execute(delete(SteamAccount).where(SteamAccount.user_id == user_id))
    return True


async def delete_user_data(session: AsyncSession, user_id: int) -> None:
    await session.execute(delete(User).where(User.id == user_id))


async def create_lobby(session: AsyncSession, chat_id: int, creator_user_id: int) -> Lobby:
    await session.execute(
        update(Lobby)
        .where(Lobby.chat_id == chat_id, Lobby.status.in_(["open", "voting"]))
        .values(status="cancelled", closed_at=func.now())
    )
    lobby = Lobby(chat_id=chat_id, creator_user_id=creator_user_id)
    session.add(lobby)
    await session.flush()
    session.add(LobbyMember(lobby_id=lobby.id, user_id=creator_user_id))
    await session.flush()
    return lobby


async def get_lobby(session: AsyncSession, lobby_id: int) -> Lobby | None:
    return await session.get(Lobby, lobby_id)


async def join_lobby(session: AsyncSession, lobby_id: int, user_id: int) -> None:
    await session.execute(
        pg_insert(LobbyMember).values(lobby_id=lobby_id, user_id=user_id).on_conflict_do_nothing()
    )


async def leave_lobby(session: AsyncSession, lobby_id: int, user_id: int) -> None:
    await session.execute(
        delete(LobbyMember).where(LobbyMember.lobby_id == lobby_id, LobbyMember.user_id == user_id)
    )
    await session.execute(
        delete(LobbyVote).where(LobbyVote.lobby_id == lobby_id, LobbyVote.user_id == user_id)
    )


async def get_lobby_members(session: AsyncSession, lobby_id: int) -> list[User]:
    return list(
        (
            await session.scalars(
                select(User)
                .join(LobbyMember, LobbyMember.user_id == User.id)
                .where(LobbyMember.lobby_id == lobby_id)
                .order_by(User.first_name)
            )
        ).all()
    )


async def replace_lobby_candidates(
    session: AsyncSession, lobby_id: int, games: list[CommonGame]
) -> list[LobbyCandidate]:
    await session.execute(delete(LobbyVote).where(LobbyVote.lobby_id == lobby_id))
    await session.execute(delete(LobbyCandidate).where(LobbyCandidate.lobby_id == lobby_id))
    candidates = [
        LobbyCandidate(lobby_id=lobby_id, app_id=game.app_id, position=index)
        for index, game in enumerate(games, start=1)
    ]
    session.add_all(candidates)
    await session.flush()
    await session.execute(update(Lobby).where(Lobby.id == lobby_id).values(status="voting"))
    return candidates


async def get_candidate_rows(
    session: AsyncSession, lobby_id: int
) -> list[tuple[LobbyCandidate, Game, int]]:
    vote_counts = (
        select(LobbyVote.candidate_id, func.count().label("votes"))
        .where(LobbyVote.lobby_id == lobby_id)
        .group_by(LobbyVote.candidate_id)
        .subquery()
    )
    rows = await session.execute(
        select(LobbyCandidate, Game, func.coalesce(vote_counts.c.votes, 0))
        .join(Game, Game.app_id == LobbyCandidate.app_id)
        .outerjoin(vote_counts, vote_counts.c.candidate_id == LobbyCandidate.id)
        .where(LobbyCandidate.lobby_id == lobby_id)
        .order_by(LobbyCandidate.position)
    )
    return [(candidate, game, int(votes)) for candidate, game, votes in rows]


async def vote_for_candidate(
    session: AsyncSession, lobby_id: int, user_id: int, candidate_id: int
) -> None:
    statement = (
        pg_insert(LobbyVote)
        .values(lobby_id=lobby_id, user_id=user_id, candidate_id=candidate_id)
        .on_conflict_do_update(
            index_elements=[LobbyVote.lobby_id, LobbyVote.user_id],
            set_={"candidate_id": candidate_id, "voted_at": func.now()},
        )
    )
    await session.execute(statement)


async def close_lobby(session: AsyncSession, lobby_id: int, winner_app_id: int) -> None:
    await session.execute(
        update(Lobby)
        .where(Lobby.id == lobby_id)
        .values(status="closed", winner_app_id=winner_app_id, closed_at=func.now())
    )


async def cancel_lobby(session: AsyncSession, lobby_id: int) -> None:
    await session.execute(
        update(Lobby).where(Lobby.id == lobby_id).values(status="cancelled", closed_at=func.now())
    )


async def add_watched_game(
    session: AsyncSession,
    user_id: int,
    app_id: int,
    name: str,
    threshold: int,
    discount: int,
    price: int | None,
    currency: str | None,
) -> None:
    statement = (
        pg_insert(WatchedGame)
        .values(
            user_id=user_id,
            app_id=app_id,
            name=name,
            threshold_percent=threshold,
            last_seen_discount=discount,
            last_seen_price=price,
            currency=currency,
            checked_at=func.now(),
        )
        .on_conflict_do_update(
            index_elements=[WatchedGame.user_id, WatchedGame.app_id],
            set_={
                "name": name,
                "threshold_percent": threshold,
                "last_seen_discount": discount,
                "last_seen_price": price,
                "currency": currency,
                "checked_at": func.now(),
            },
        )
    )
    await session.execute(statement)


async def get_watched_games(session: AsyncSession, user_id: int) -> list[WatchedGame]:
    return list(
        (
            await session.scalars(
                select(WatchedGame).where(WatchedGame.user_id == user_id).order_by(WatchedGame.name)
            )
        ).all()
    )


async def remove_watched_game(session: AsyncSession, user_id: int, app_id: int) -> bool:
    exists = await session.scalar(
        select(WatchedGame.id).where(WatchedGame.user_id == user_id, WatchedGame.app_id == app_id)
    )
    if exists is None:
        return False
    await session.execute(
        delete(WatchedGame).where(WatchedGame.user_id == user_id, WatchedGame.app_id == app_id)
    )
    return True


async def set_digest_subscription(
    session: AsyncSession,
    user_id: int,
    min_discount: int,
    deals_enabled: bool,
    releases_enabled: bool,
) -> DigestSubscription:
    statement = (
        pg_insert(DigestSubscription)
        .values(
            user_id=user_id,
            min_discount=min_discount,
            deals_enabled=deals_enabled,
            releases_enabled=releases_enabled,
        )
        .on_conflict_do_update(
            index_elements=[DigestSubscription.user_id],
            set_={
                "min_discount": min_discount,
                "deals_enabled": deals_enabled,
                "releases_enabled": releases_enabled,
                "updated_at": func.now(),
            },
        )
        .returning(DigestSubscription)
    )
    return (await session.execute(statement)).scalar_one()


async def get_digest_subscription(session: AsyncSession, user_id: int) -> DigestSubscription | None:
    return await session.get(DigestSubscription, user_id)


async def remove_digest_subscription(session: AsyncSession, user_id: int) -> bool:
    existing = await session.get(DigestSubscription, user_id)
    if existing is None:
        return False
    await session.delete(existing)
    return True


async def get_digest_recipients(
    session: AsyncSession,
) -> list[tuple[DigestSubscription, User]]:
    return list(
        (
            await session.execute(
                select(DigestSubscription, User)
                .join(User, User.id == DigestSubscription.user_id)
                .where(
                    (DigestSubscription.deals_enabled.is_(True))
                    | (DigestSubscription.releases_enabled.is_(True))
                )
                .order_by(User.id)
            )
        ).tuples()
    )
