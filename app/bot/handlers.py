import html
import re
from typing import Any

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards import LobbyAction, LobbyVote, lobby_open_keyboard, voting_keyboard
from app.clients.steam import SteamApiError, SteamClient
from app.clients.store import SteamStoreClient, StoreApiError
from app.db import repositories as repo
from app.db.models import User, UserGame
from app.services.game_picker import pick_candidates, select_winner

router = Router()

HELP_TEXT = """<b>«Во что?» — Steam-помощник для компании</b>

/link &lt;SteamID или ссылка&gt; — привязать Steam
/sync — обновить библиотеку
/profile — мой профиль
/online — кто играет в группе
/common — общие игры группы
/lobby — собрать лобби и выбрать игру
/watch &lt;AppID&gt; &lt;25|50|75&gt; — следить за скидкой
/watchlist — мои уведомления
/unwatch &lt;AppID&gt; — удалить уведомление"""


def is_group(message: Message) -> bool:
    return message.chat.type in {"group", "supergroup"}


async def ensure_context(
    session: AsyncSession, telegram_user: Any, telegram_chat: Any
) -> tuple[User, Any]:
    user = await repo.ensure_user(session, telegram_user)
    chat = await repo.ensure_chat(session, telegram_chat)
    if telegram_chat.type in {"group", "supergroup"}:
        await repo.activate_chat_member(session, chat.id, user.id)
    return user, chat


def command_args(message: Message) -> list[str]:
    text = message.text or ""
    return text.split(maxsplit=1)[1].split() if len(text.split(maxsplit=1)) > 1 else []


def parse_app_id(value: str) -> int | None:
    if value.isdigit():
        return int(value)
    match = re.search(r"store\.steampowered\.com/app/(\d+)", value)
    return int(match.group(1)) if match else None


def format_price(value: int | None, currency: str | None) -> str:
    if value is None:
        return "цена недоступна"
    return f"{value / 100:.2f} {currency or ''}".strip()


async def render_open_lobby(session: AsyncSession, lobby_id: int) -> str:
    members = await repo.get_lobby_members(session, lobby_id)
    names = ", ".join(html.escape(member.first_name) for member in members) or "пока никого"
    return (
        "<b>🎮 Собираем лобби</b>\n\n"
        f"Участники ({len(members)}): {names}\n\n"
        "Нажмите «Я играю». Создатель затем подберёт три общие игры."
    )


async def render_voting(
    session: AsyncSession, lobby_id: int
) -> tuple[str, list[tuple[int, str, int]]]:
    rows = await repo.get_candidate_rows(session, lobby_id)
    candidates = [(candidate.id, game.name, votes) for candidate, game, votes in rows]
    lines = ["<b>🗳 Выберите игру</b>", ""]
    for index, (_candidate_id, name, votes) in enumerate(candidates, start=1):
        lines.append(f"{index}. <b>{html.escape(name)}</b> — {votes} голос(ов)")
    lines.extend(["", "Создатель лобби завершает голосование."])
    return "\n".join(lines), candidates


@router.message(CommandStart())
@router.message(Command("help"))
async def start_handler(message: Message, session: AsyncSession) -> None:
    if not message.from_user:
        return
    await ensure_context(session, message.from_user, message.chat)
    await message.answer(HELP_TEXT)


@router.message(Command("link"))
async def link_handler(message: Message, session: AsyncSession, steam: SteamClient) -> None:
    if not message.from_user:
        return
    user, _chat = await ensure_context(session, message.from_user, message.chat)
    args = command_args(message)
    if not args:
        await message.answer("Использование: <code>/link ссылка_на_Steam_профиль</code>")
        return
    try:
        steam_id = await steam.resolve_profile_input(args[0])
        profile = await steam.get_profile(steam_id)
        games = await steam.get_owned_games(steam_id)
        await repo.link_steam_account(session, user.id, profile)
        await repo.sync_user_games(session, user.id, games)
    except (SteamApiError, ValueError) as exc:
        await message.answer(f"Не получилось привязать профиль: {html.escape(str(exc))}")
        return
    await message.answer(
        f"✅ Привязан <b>{html.escape(profile.name)}</b>\nСинхронизировано игр: {len(games)}"
    )


@router.message(Command("sync"))
async def sync_handler(message: Message, session: AsyncSession, steam: SteamClient) -> None:
    if not message.from_user:
        return
    user, _chat = await ensure_context(session, message.from_user, message.chat)
    account = await repo.get_steam_account(session, user.id)
    if not account:
        await message.answer("Сначала привяжите Steam: <code>/link ссылка</code>")
        return
    try:
        games = await steam.get_owned_games(account.steam_id)
        profile = await steam.get_profile(account.steam_id)
        await repo.link_steam_account(session, user.id, profile)
        await repo.sync_user_games(session, user.id, games)
    except SteamApiError as exc:
        await message.answer(html.escape(str(exc)))
        return
    await message.answer(f"✅ Библиотека обновлена: {len(games)} игр")


@router.message(Command("profile"))
async def profile_handler(message: Message, session: AsyncSession, steam: SteamClient) -> None:
    if not message.from_user:
        return
    user, _chat = await ensure_context(session, message.from_user, message.chat)
    account = await repo.get_steam_account(session, user.id)
    if not account:
        await message.answer("Сначала привяжите Steam: <code>/link ссылка</code>")
        return
    try:
        profile = await steam.get_profile(account.steam_id)
    except SteamApiError as exc:
        await message.answer(html.escape(str(exc)))
        return
    stats = (
        await session.execute(
            select(
                func.count(UserGame.app_id), func.coalesce(func.sum(UserGame.playtime_forever), 0)
            ).where(UserGame.user_id == user.id)
        )
    ).one()
    status = f"играет в {html.escape(profile.game_name)}" if profile.game_name else "не играет"
    await message.answer(
        f"<b>🎮 {html.escape(profile.name)}</b>\n"
        f"Сейчас: {status}\n"
        f"Игр: {stats[0]}\n"
        f"Общее время: {int(stats[1]) // 60} ч\n"
        f'<a href="{html.escape(profile.profile_url)}">Открыть профиль</a>'
    )


@router.message(Command("online"))
async def online_handler(message: Message, session: AsyncSession, steam: SteamClient) -> None:
    if not message.from_user:
        return
    _user, chat = await ensure_context(session, message.from_user, message.chat)
    if not is_group(message):
        await message.answer("Команда работает в групповом чате.")
        return
    linked = await repo.get_chat_linked_users(session, chat.id)
    try:
        profiles = await steam.get_profiles([account.steam_id for _user, account in linked])
    except SteamApiError as exc:
        await message.answer(html.escape(str(exc)))
        return
    by_id = {profile.steam_id: profile for profile in profiles}
    lines = ["<b>🟢 Статус участников</b>", ""]
    for user, account in linked:
        profile = by_id.get(account.steam_id)
        if not profile:
            continue
        state = (
            f"🎮 {profile.game_name}"
            if profile.game_name
            else ("🟢 онлайн" if profile.persona_state else "⚫ офлайн")
        )
        lines.append(f"• {html.escape(user.first_name)} — {html.escape(state)}")
    if not linked:
        lines.append("Никто ещё не привязал Steam через /link.")
    await message.answer("\n".join(lines))


@router.message(Command("common"))
async def common_handler(message: Message, session: AsyncSession) -> None:
    if not message.from_user:
        return
    _user, chat = await ensure_context(session, message.from_user, message.chat)
    if not is_group(message):
        await message.answer("Команда работает в групповом чате.")
        return
    linked = await repo.get_chat_linked_users(session, chat.id)
    if len(linked) < 2:
        await message.answer("Нужно хотя бы два участника с привязанным Steam.")
        return
    games = await repo.get_common_games(session, [user.id for user, _account in linked])
    lines = [f"<b>Общих игр: {len(games)}</b>", ""]
    for game in games[:20]:
        lines.append(f"• {html.escape(game.name)}")
    if len(games) > 20:
        lines.append(f"…и ещё {len(games) - 20}")
    await message.answer("\n".join(lines))


@router.message(Command("lobby"))
async def lobby_handler(message: Message, session: AsyncSession) -> None:
    if not message.from_user:
        return
    user, chat = await ensure_context(session, message.from_user, message.chat)
    if not is_group(message):
        await message.answer("Создайте лобби в групповом чате.")
        return
    if not await repo.get_steam_account(session, user.id):
        await message.answer("Сначала привяжите Steam: <code>/link ссылка</code>")
        return
    lobby = await repo.create_lobby(session, chat.id, user.id)
    text = await render_open_lobby(session, lobby.id)
    await message.answer(text, reply_markup=lobby_open_keyboard(lobby.id))


@router.callback_query(LobbyAction.filter(F.action.in_({"join", "leave"})))
async def lobby_member_callback(
    callback: CallbackQuery,
    callback_data: LobbyAction,
    session: AsyncSession,
) -> None:
    if not callback.from_user or not isinstance(callback.message, Message):
        return
    user, _chat = await ensure_context(session, callback.from_user, callback.message.chat)
    lobby = await repo.get_lobby(session, callback_data.lobby_id)
    if not lobby or lobby.status != "open":
        await callback.answer("Лобби уже закрыто", show_alert=True)
        return
    if callback_data.action == "join":
        if not await repo.get_steam_account(session, user.id):
            await callback.answer("Сначала привяжите Steam через /link", show_alert=True)
            return
        await repo.join_lobby(session, lobby.id, user.id)
        answer = "Вы участвуете"
    else:
        if user.id == lobby.creator_user_id:
            await callback.answer("Создатель не может выйти — отмените лобби", show_alert=True)
            return
        await repo.leave_lobby(session, lobby.id, user.id)
        answer = "Вы вышли"
    await session.flush()
    text = await render_open_lobby(session, lobby.id)
    await callback.message.edit_text(text, reply_markup=lobby_open_keyboard(lobby.id))
    await callback.answer(answer)


@router.callback_query(LobbyAction.filter(F.action == "pick"))
async def lobby_pick_callback(
    callback: CallbackQuery,
    callback_data: LobbyAction,
    session: AsyncSession,
) -> None:
    if not isinstance(callback.message, Message):
        return
    user, _chat = await ensure_context(session, callback.from_user, callback.message.chat)
    lobby = await repo.get_lobby(session, callback_data.lobby_id)
    if not lobby or lobby.status != "open":
        await callback.answer("Лобби уже изменилось", show_alert=True)
        return
    if user.id != lobby.creator_user_id:
        await callback.answer("Игры выбирает создатель лобби", show_alert=True)
        return
    members = await repo.get_lobby_members(session, lobby.id)
    if len(members) < 2:
        await callback.answer("Нужно хотя бы два участника", show_alert=True)
        return
    games = await repo.get_common_games(session, [member.id for member in members])
    chosen = pick_candidates(games)
    if not chosen:
        await callback.answer(
            "Общих игр не найдено. Обновите библиотеки через /sync", show_alert=True
        )
        return
    await repo.replace_lobby_candidates(session, lobby.id, chosen)
    await session.flush()
    text, candidates = await render_voting(session, lobby.id)
    await callback.message.edit_text(text, reply_markup=voting_keyboard(lobby.id, candidates))
    await callback.answer()


@router.callback_query(LobbyVote.filter())
async def lobby_vote_callback(
    callback: CallbackQuery,
    callback_data: LobbyVote,
    session: AsyncSession,
) -> None:
    if not isinstance(callback.message, Message):
        return
    user, _chat = await ensure_context(session, callback.from_user, callback.message.chat)
    lobby = await repo.get_lobby(session, callback_data.lobby_id)
    if not lobby or lobby.status != "voting":
        await callback.answer("Голосование закрыто", show_alert=True)
        return
    member_ids = {member.id for member in await repo.get_lobby_members(session, lobby.id)}
    candidates = await repo.get_candidate_rows(session, lobby.id)
    valid_candidate_ids = {candidate.id for candidate, _game, _votes in candidates}
    if user.id not in member_ids:
        await callback.answer("Сначала присоединитесь к лобби", show_alert=True)
        return
    if callback_data.candidate_id not in valid_candidate_ids:
        await callback.answer("Вариант не найден", show_alert=True)
        return
    await repo.vote_for_candidate(session, lobby.id, user.id, callback_data.candidate_id)
    await session.flush()
    text, candidate_buttons = await render_voting(session, lobby.id)
    await callback.message.edit_text(
        text, reply_markup=voting_keyboard(lobby.id, candidate_buttons)
    )
    await callback.answer("Голос принят")


@router.callback_query(LobbyAction.filter(F.action == "finish"))
async def lobby_finish_callback(
    callback: CallbackQuery,
    callback_data: LobbyAction,
    session: AsyncSession,
) -> None:
    if not isinstance(callback.message, Message):
        return
    user, _chat = await ensure_context(session, callback.from_user, callback.message.chat)
    lobby = await repo.get_lobby(session, callback_data.lobby_id)
    if not lobby or lobby.status != "voting":
        await callback.answer("Голосование уже закрыто", show_alert=True)
        return
    if user.id != lobby.creator_user_id:
        await callback.answer("Завершить может только создатель", show_alert=True)
        return
    rows = await repo.get_candidate_rows(session, lobby.id)
    _winner_candidate, winner_game, winner_votes = select_winner(
        [((candidate, game, votes), votes) for candidate, game, votes in rows]
    )
    await repo.close_lobby(session, lobby.id, winner_game.app_id)
    await callback.message.edit_text(
        f"<b>🏆 Сегодня играем в {html.escape(winner_game.name)}</b>\n\n"
        f"Голосов: {winner_votes}\n"
        f'<a href="https://store.steampowered.com/app/{winner_game.app_id}">Открыть в Steam</a>'
    )
    await callback.answer("Игра выбрана")


@router.callback_query(LobbyAction.filter(F.action == "cancel"))
async def lobby_cancel_callback(
    callback: CallbackQuery,
    callback_data: LobbyAction,
    session: AsyncSession,
) -> None:
    if not isinstance(callback.message, Message):
        return
    user, _chat = await ensure_context(session, callback.from_user, callback.message.chat)
    lobby = await repo.get_lobby(session, callback_data.lobby_id)
    if not lobby or lobby.status not in {"open", "voting"}:
        await callback.answer("Лобби уже закрыто", show_alert=True)
        return
    if user.id != lobby.creator_user_id:
        await callback.answer("Отменить может только создатель", show_alert=True)
        return
    await repo.cancel_lobby(session, lobby.id)
    await callback.message.edit_text("Лобби отменено.")
    await callback.answer()


@router.message(Command("watch"))
async def watch_handler(
    message: Message,
    session: AsyncSession,
    store: SteamStoreClient,
) -> None:
    if not message.from_user:
        return
    user, _chat = await ensure_context(session, message.from_user, message.chat)
    if message.chat.type != "private":
        await message.answer("Настройте скидки в личном чате с ботом.")
        return
    args = command_args(message)
    if not args or (app_id := parse_app_id(args[0])) is None:
        await message.answer("Использование: <code>/watch AppID 25|50|75</code>")
        return
    threshold = int(args[1]) if len(args) > 1 and args[1].isdigit() else 50
    if threshold not in {25, 50, 75}:
        await message.answer("Порог скидки: 25, 50 или 75 процентов.")
        return
    try:
        offer = await store.get_offer(app_id)
    except StoreApiError as exc:
        await message.answer(html.escape(str(exc)))
        return
    await repo.add_watched_game(
        session,
        user.id,
        app_id,
        offer.name,
        threshold,
        offer.discount_percent,
        offer.final_price,
        offer.currency,
    )
    await message.answer(
        f"🔔 <b>{html.escape(offer.name)}</b>\n"
        f"Сообщу при скидке от {threshold}%. Сейчас: {offer.discount_percent}%."
    )


@router.message(Command("watchlist"))
async def watchlist_handler(message: Message, session: AsyncSession) -> None:
    if not message.from_user:
        return
    user, _chat = await ensure_context(session, message.from_user, message.chat)
    watched = await repo.get_watched_games(session, user.id)
    if not watched:
        await message.answer("Список пуст. Добавьте игру: <code>/watch AppID 50</code>")
        return
    lines = ["<b>🔔 Отслеживаемые скидки</b>", ""]
    for item in watched:
        current = format_price(item.last_seen_price, item.currency)
        lines.append(
            f"• {html.escape(item.name)} — от {item.threshold_percent}% "
            f"(сейчас {item.last_seen_discount}%, {current})"
        )
    await message.answer("\n".join(lines))


@router.message(Command("unwatch"))
async def unwatch_handler(message: Message, session: AsyncSession) -> None:
    if not message.from_user:
        return
    user, _chat = await ensure_context(session, message.from_user, message.chat)
    args = command_args(message)
    app_id = parse_app_id(args[0]) if args else None
    if app_id is None:
        await message.answer("Использование: <code>/unwatch AppID</code>")
        return
    removed = await repo.remove_watched_game(session, user.id, app_id)
    await message.answer("Удалено." if removed else "Такой игры нет в списке.")
