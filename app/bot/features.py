import asyncio
import html
import random

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.filters.callback_data import CallbackData
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers import command_args, ensure_context, format_price, is_group, parse_app_id
from app.bot.safety import safe_edit_text
from app.clients.steam import SteamApiError, SteamClient
from app.clients.store import SteamStoreClient, StoreApiError, StoreCatalogItem, StoreOffer
from app.db import repositories as repo
from app.db.models import SteamAccount
from app.services.catalog import select_deals, select_releases
from app.services.game_picker import pick_candidates

router = Router()


class DataAction(CallbackData, prefix="data"):
    operation: str
    action: str


def confirmation_keyboard(operation: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Да, удалить",
                    callback_data=DataAction(operation=operation, action="confirm").pack(),
                ),
                InlineKeyboardButton(
                    text="Отмена",
                    callback_data=DataAction(operation=operation, action="cancel").pack(),
                ),
            ]
        ]
    )


def catalog_item_line(item: StoreCatalogItem) -> str:
    price = format_price(item.final_price, item.currency)
    return (
        f'• <a href="https://store.steampowered.com/app/{item.app_id}">'
        f"{html.escape(item.name)}</a> — {item.discount_percent}%, {price}"
    )


async def require_account(
    session: AsyncSession, user_id: int, message: Message
) -> SteamAccount | None:
    account = await repo.get_steam_account(session, user_id)
    if not account:
        await message.answer("Сначала привяжите Steam: <code>/link ссылка</code>")
    return account


@router.message(Command("random"))
async def random_game_handler(message: Message, session: AsyncSession) -> None:
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
    chosen = pick_candidates(games, count=1)
    if not chosen:
        await message.answer("Общих игр не найдено.")
        return
    game = chosen[0]
    await message.answer(
        f"<b>🎲 Игра выбрана: {html.escape(game.name)}</b>\n"
        f'<a href="https://store.steampowered.com/app/{game.app_id}">Открыть в Steam</a>'
    )


@router.message(Command("whoowns"))
async def who_owns_handler(
    message: Message,
    session: AsyncSession,
    store: SteamStoreClient,
) -> None:
    if not message.from_user:
        return
    _user, chat = await ensure_context(session, message.from_user, message.chat)
    if not is_group(message):
        await message.answer("Команда работает в групповом чате.")
        return
    args = command_args(message)
    app_id = parse_app_id(args[0]) if args else None
    if app_id is None:
        await message.answer("Использование: <code>/whoowns AppID</code>")
        return
    try:
        offer = await store.get_offer(app_id)
    except StoreApiError as exc:
        await message.answer(html.escape(str(exc)))
        return
    ownership = await repo.get_chat_game_ownership(session, chat.id, app_id)
    lines = [f"<b>🎮 {html.escape(offer.name)}</b>", ""]
    lines.extend(
        f"{'✅' if owned else '❌'} {html.escape(user.first_name)}" for user, owned in ownership
    )
    if not ownership:
        lines.append("В группе ещё никто не привязал Steam.")
    await message.answer("\n".join(lines))


@router.message(Command("backlog"))
async def backlog_handler(message: Message, session: AsyncSession) -> None:
    if not message.from_user:
        return
    user, _chat = await ensure_context(session, message.from_user, message.chat)
    if not await require_account(session, user.id, message):
        return
    games = await repo.get_user_backlog(session, user.id)
    if not games:
        await message.answer("В синхронизированной библиотеке нет неигранных игр.")
        return
    selected = random.sample(games, k=min(10, len(games)))
    lines = [f"<b>🕸 Не запускались: {len(games)}</b>", ""]
    lines.extend(
        f'• <a href="https://store.steampowered.com/app/{game.app_id}">{html.escape(game.name)}</a>'
        for game in selected
    )
    await message.answer("\n".join(lines))


@router.message(Command("stats"))
async def stats_handler(message: Message, session: AsyncSession) -> None:
    if not message.from_user:
        return
    user, _chat = await ensure_context(session, message.from_user, message.chat)
    if not await require_account(session, user.id, message):
        return
    stats = await repo.get_library_stats(session, user.id)
    played_percent = (
        round((stats.total_games - stats.unplayed_games) / stats.total_games * 100)
        if stats.total_games
        else 0
    )
    await message.answer(
        "<b>📊 Статистика библиотеки</b>\n\n"
        f"Игр: {stats.total_games}\n"
        f"Общее время: {stats.total_minutes // 60} ч\n"
        f"Не запускались: {stats.unplayed_games}\n"
        f"Запущено: {played_percent}% библиотеки\n"
        f"За две недели: {stats.recent_minutes / 60:.1f} ч"
    )


@router.message(Command("level"))
async def level_handler(message: Message, session: AsyncSession, steam: SteamClient) -> None:
    if not message.from_user:
        return
    user, _chat = await ensure_context(session, message.from_user, message.chat)
    account = await require_account(session, user.id, message)
    if not account:
        return
    try:
        level = await steam.get_steam_level(account.steam_id)
    except SteamApiError as exc:
        await message.answer(html.escape(str(exc)))
        return
    await message.answer(f"<b>⭐ Уровень Steam: {level}</b>")


@router.message(Command("compare"))
async def compare_handler(message: Message, session: AsyncSession) -> None:
    if not message.from_user:
        return
    user, _chat = await ensure_context(session, message.from_user, message.chat)
    if (
        not is_group(message)
        or not message.reply_to_message
        or not message.reply_to_message.from_user
    ):
        await message.answer("В группе ответьте командой /compare на сообщение другого участника.")
        return
    target_telegram = message.reply_to_message.from_user
    if target_telegram.id == message.from_user.id:
        await message.answer("Выберите другого участника.")
        return
    target, _target_chat = await ensure_context(session, target_telegram, message.chat)
    if not await repo.get_steam_account(session, user.id):
        await message.answer("Сначала привяжите свой Steam через /link.")
        return
    if not await repo.get_steam_account(session, target.id):
        await message.answer("У выбранного участника Steam ещё не привязан.")
        return
    first_games = await repo.get_user_game_ids(session, user.id)
    second_games = await repo.get_user_game_ids(session, target.id)
    common_ids = first_games & second_games
    all_ids = first_games | second_games
    compatibility = round(len(common_ids) / len(all_ids) * 100) if all_ids else 0
    common_games = await repo.get_common_games(session, [user.id, target.id])
    favorites = sorted(common_games, key=lambda game: game.total_playtime, reverse=True)[:5]
    lines = [
        f"<b>{html.escape(user.first_name)} × {html.escape(target.first_name)}</b>",
        "",
        f"Совпадение библиотек: {compatibility}%",
        f"Общих игр: {len(common_ids)}",
    ]
    if favorites:
        lines.extend(["", "Общие любимые:"])
        lines.extend(f"• {html.escape(game.name)}" for game in favorites)
    await message.answer("\n".join(lines))


@router.message(Command("recent"))
async def recent_handler(message: Message, session: AsyncSession, steam: SteamClient) -> None:
    if not message.from_user:
        return
    user, _chat = await ensure_context(session, message.from_user, message.chat)
    account = await require_account(session, user.id, message)
    if not account:
        return
    try:
        games = await steam.get_recently_played(account.steam_id, count=10)
    except SteamApiError as exc:
        await message.answer(html.escape(str(exc)))
        return
    if not games:
        await message.answer("Недавние игры скрыты или список пуст.")
        return
    lines = ["<b>🕒 Недавние игры</b>", ""]
    for game in games:
        recent_hours = (game.playtime_two_weeks or 0) / 60
        lines.append(f"• {html.escape(game.name)} — {recent_hours:.1f} ч за 2 недели")
    await message.answer("\n".join(lines))


@router.message(Command("achievements"))
async def achievements_handler(
    message: Message,
    session: AsyncSession,
    steam: SteamClient,
) -> None:
    if not message.from_user:
        return
    user, _chat = await ensure_context(session, message.from_user, message.chat)
    account = await require_account(session, user.id, message)
    if not account:
        return
    args = command_args(message)
    app_id = parse_app_id(args[0]) if args else None
    if app_id is None:
        await message.answer("Использование: <code>/achievements AppID</code>")
        return
    try:
        achievements = await steam.get_achievements(account.steam_id, app_id)
    except SteamApiError as exc:
        await message.answer(html.escape(str(exc)))
        return
    if not achievements:
        await message.answer("У игры нет доступных достижений.")
        return
    unlocked = [item for item in achievements if item.achieved]
    latest = sorted(unlocked, key=lambda item: item.unlock_time, reverse=True)[:8]
    lines = [f"<b>🏆 Достижения: {len(unlocked)}/{len(achievements)}</b>", ""]
    if latest:
        lines.append("Последние полученные:")
        lines.extend(f"• {html.escape(item.name)}" for item in latest)
    await message.answer("\n".join(lines))


@router.message(Command("game"))
async def game_handler(
    message: Message,
    session: AsyncSession,
    steam: SteamClient,
    store: SteamStoreClient,
) -> None:
    if not message.from_user:
        return
    await ensure_context(session, message.from_user, message.chat)
    args = command_args(message)
    app_id = parse_app_id(args[0]) if args else None
    if app_id is None:
        await message.answer("Использование: <code>/game AppID</code>")
        return
    try:
        offer = await store.get_offer(app_id)
    except StoreApiError as exc:
        await message.answer(html.escape(str(exc)))
        return
    try:
        current_players: int | None = await steam.get_current_players(app_id)
    except SteamApiError:
        current_players = None
    price = "бесплатно" if offer.is_free else format_price(offer.final_price, offer.currency)
    genres = ", ".join(offer.genres[:4]) or "не указаны"
    online = f"{current_players:,}".replace(",", " ") if current_players is not None else "н/д"
    description = html.escape(offer.short_description[:500])
    await message.answer(
        f"<b>🎮 {html.escape(offer.name)}</b>\n\n"
        f"{description}\n\n"
        f"Жанры: {html.escape(genres)}\n"
        f"Онлайн: {online}\n"
        f"Цена: {price}\n"
        f"Скидка: {offer.discount_percent}%\n"
        f"Релиз: {html.escape(offer.release_date or 'не указан')}\n"
        f'<a href="https://store.steampowered.com/app/{app_id}">Открыть в Steam</a>'
    )


@router.message(Command("deals"))
async def deals_handler(
    message: Message,
    session: AsyncSession,
    store: SteamStoreClient,
) -> None:
    if not message.from_user:
        return
    await ensure_context(session, message.from_user, message.chat)
    args = command_args(message)
    threshold = int(args[0]) if args and args[0].isdigit() else 50
    if threshold not in {25, 50, 75}:
        await message.answer("Порог скидки: 25, 50 или 75 процентов.")
        return
    try:
        catalog = await store.get_featured_catalog()
    except StoreApiError as exc:
        await message.answer(html.escape(str(exc)))
        return
    deals = select_deals(catalog, threshold)
    if not deals:
        await message.answer(f"Сейчас нет предложений со скидкой от {threshold}%.")
        return
    lines = [f"<b>🔥 Выгодные предложения от {threshold}%</b>", ""]
    lines.extend(catalog_item_line(item) for item in deals)
    await message.answer("\n".join(lines))


@router.message(Command("releases"))
async def releases_handler(
    message: Message,
    session: AsyncSession,
    store: SteamStoreClient,
) -> None:
    if not message.from_user:
        return
    await ensure_context(session, message.from_user, message.chat)
    try:
        catalog = await store.get_featured_catalog()
    except StoreApiError as exc:
        await message.answer(html.escape(str(exc)))
        return
    releases = select_releases(catalog, count=5)
    if not releases:
        await message.answer("Новые релизы сейчас недоступны.")
        return
    details = await asyncio.gather(
        *(store.get_offer(item.app_id) for item in releases[:3]),
        return_exceptions=True,
    )
    detail_by_id = {detail.app_id: detail for detail in details if isinstance(detail, StoreOffer)}
    lines = ["<b>🚀 Заметные новые релизы</b>", ""]
    for item in releases:
        lines.append(
            f'<a href="https://store.steampowered.com/app/{item.app_id}">'
            f"<b>{html.escape(item.name)}</b></a>"
        )
        if detail := detail_by_id.get(item.app_id):
            genres = ", ".join(detail.genres[:3])
            if genres:
                lines.append(f"{html.escape(genres)}")
            if detail.short_description:
                lines.append(html.escape(detail.short_description[:180]))
        lines.append("")
    await message.answer("\n".join(lines).rstrip())


@router.message(Command("digest"))
async def digest_handler(message: Message, session: AsyncSession) -> None:
    if not message.from_user:
        return
    user, _chat = await ensure_context(session, message.from_user, message.chat)
    if message.chat.type != "private":
        await message.answer("Настройте дайджест в личном чате с ботом.")
        return
    args = [arg.lower() for arg in command_args(message)]
    action = args[0] if args else "status"
    if action == "off":
        removed = await repo.remove_digest_subscription(session, user.id)
        await message.answer("Дайджест отключён." if removed else "Дайджест уже отключён.")
        return
    if action == "status":
        subscription = await repo.get_digest_subscription(session, user.id)
        if not subscription:
            await message.answer("Дайджест отключён. Включить: <code>/digest all 50</code>")
            return
        modes = []
        if subscription.deals_enabled:
            modes.append("скидки")
        if subscription.releases_enabled:
            modes.append("релизы")
        await message.answer(
            f"Дайджест включён: {', '.join(modes)}. Порог скидки: {subscription.min_discount}%."
        )
        return
    if action not in {"on", "all", "deals", "releases"}:
        await message.answer(
            "Использование:\n"
            "<code>/digest all 50</code> — скидки и релизы\n"
            "<code>/digest deals 75</code> — только скидки\n"
            "<code>/digest releases</code> — только релизы\n"
            "<code>/digest off</code> — отключить"
        )
        return
    threshold = int(args[1]) if len(args) > 1 and args[1].isdigit() else 50
    if threshold not in {25, 50, 75}:
        await message.answer("Порог скидки: 25, 50 или 75 процентов.")
        return
    deals_enabled = action in {"on", "all", "deals"}
    releases_enabled = action in {"on", "all", "releases"}
    await repo.set_digest_subscription(
        session,
        user.id,
        threshold,
        deals_enabled=deals_enabled,
        releases_enabled=releases_enabled,
    )
    await message.answer(
        "✅ Ежедневный дайджест включён. Проверить настройки: <code>/digest status</code>"
    )


@router.message(Command("news"))
async def news_handler(message: Message, session: AsyncSession, steam: SteamClient) -> None:
    if not message.from_user:
        return
    await ensure_context(session, message.from_user, message.chat)
    args = command_args(message)
    app_id = parse_app_id(args[0]) if args else None
    if app_id is None:
        await message.answer("Использование: <code>/news AppID</code>")
        return
    try:
        news = await steam.get_news(app_id, count=3)
    except SteamApiError as exc:
        await message.answer(html.escape(str(exc)))
        return
    if not news:
        await message.answer("Новости для этой игры не найдены.")
        return
    lines = ["<b>📰 Последние новости</b>", ""]
    for item in news:
        date = item.published_at.strftime("%d.%m.%Y")
        safe_url = html.escape(item.url, quote=True)
        lines.append(f'• <a href="{safe_url}">{html.escape(item.title)}</a> — {date}')
    await message.answer("\n".join(lines))


@router.message(Command("bans"))
async def bans_handler(message: Message, session: AsyncSession, steam: SteamClient) -> None:
    if not message.from_user:
        return
    user, _chat = await ensure_context(session, message.from_user, message.chat)
    account = await require_account(session, user.id, message)
    if not account:
        return
    try:
        bans = await steam.get_player_bans(account.steam_id)
    except SteamApiError as exc:
        await message.answer(html.escape(str(exc)))
        return
    await message.answer(
        "<b>🛡 Проверка блокировок</b>\n\n"
        f"VAC: {'да' if bans.vac_banned else 'нет'} ({bans.vac_bans})\n"
        f"Игровые: {bans.game_bans}\n"
        f"Community ban: {'да' if bans.community_banned else 'нет'}\n"
        f"Ограничение обмена: {html.escape(bans.economy_ban)}"
    )


@router.message(Command("privacy"))
async def privacy_handler(message: Message) -> None:
    await message.answer(
        "<b>Приватность</b>\n\n"
        "Бот хранит Telegram ID, привязанный SteamID, синхронизированную библиотеку, "
        "голоса в лобби и настройки скидок. Пароли и платёжные данные не запрашиваются.\n\n"
        "/unlink — удалить связь со Steam и библиотеку\n"
        "/delete_me — полностью удалить свои данные"
    )


@router.message(Command("unlink"))
async def unlink_handler(message: Message) -> None:
    if message.chat.type != "private":
        await message.answer("Удаление данных доступно только в личном чате.")
        return
    await message.answer(
        "Удалить привязку Steam и синхронизированную библиотеку?",
        reply_markup=confirmation_keyboard("unlink"),
    )


@router.message(Command("delete_me"))
async def delete_me_handler(message: Message) -> None:
    if message.chat.type != "private":
        await message.answer("Удаление данных доступно только в личном чате.")
        return
    await message.answer(
        "Полностью удалить профиль, библиотеку, голоса и уведомления? Это необратимо.",
        reply_markup=confirmation_keyboard("delete"),
    )


@router.callback_query(DataAction.filter(F.action == "cancel"))
async def data_cancel_callback(callback: CallbackQuery) -> None:
    if isinstance(callback.message, Message):
        await safe_edit_text(callback.message, "Удаление отменено.")
    await callback.answer()


@router.callback_query(DataAction.filter(F.action == "confirm"))
async def data_confirm_callback(
    callback: CallbackQuery,
    callback_data: DataAction,
    session: AsyncSession,
) -> None:
    if not isinstance(callback.message, Message):
        return
    if callback.message.chat.type != "private":
        await callback.answer("Недоступно в группе", show_alert=True)
        return
    user, _chat = await ensure_context(session, callback.from_user, callback.message.chat)
    if callback_data.operation == "unlink":
        removed = await repo.unlink_steam_account(session, user.id)
        text = "Привязка Steam и библиотека удалены." if removed else "Steam не был привязан."
    elif callback_data.operation == "delete":
        await repo.delete_user_data(session, user.id)
        text = "Все ваши данные удалены. Команда /start создаст новый профиль."
    else:
        await callback.answer("Неизвестная операция", show_alert=True)
        return
    await safe_edit_text(callback.message, text)
    await callback.answer("Готово")
