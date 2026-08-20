import asyncio
import logging

import httpx
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from app.bot.features import router as features_router
from app.bot.handlers import router as core_router
from app.bot.middleware import DbSessionMiddleware
from app.bot.safety import handle_unexpected_error
from app.bot.throttling import ThrottlingMiddleware
from app.clients.steam import SteamClient
from app.clients.store import SteamStoreClient
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import engine

logger = logging.getLogger(__name__)


async def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML, link_preview_is_disabled=True),
    )
    dispatcher = Dispatcher()
    dispatcher.update.outer_middleware(DbSessionMiddleware())
    dispatcher.message.outer_middleware(ThrottlingMiddleware())
    dispatcher.callback_query.outer_middleware(ThrottlingMiddleware())
    dispatcher.errors.register(handle_unexpected_error)
    dispatcher.include_router(core_router)
    dispatcher.include_router(features_router)

    await bot.set_my_commands(
        [
            BotCommand(command="link", description="Привязать Steam-профиль"),
            BotCommand(command="profile", description="Мой Steam-профиль"),
            BotCommand(command="sync", description="Обновить библиотеку"),
            BotCommand(command="lobby", description="Собрать игровое лобби"),
            BotCommand(command="common", description="Общие игры группы"),
            BotCommand(command="random", description="Выбрать общую игру"),
            BotCommand(command="whoowns", description="У кого есть игра"),
            BotCommand(command="online", description="Кто сейчас играет"),
            BotCommand(command="backlog", description="Неигранные игры"),
            BotCommand(command="stats", description="Статистика библиотеки"),
            BotCommand(command="level", description="Уровень Steam"),
            BotCommand(command="compare", description="Сравнить игроков"),
            BotCommand(command="recent", description="Недавние игры"),
            BotCommand(command="achievements", description="Достижения игры"),
            BotCommand(command="game", description="Информация об игре"),
            BotCommand(command="news", description="Новости игры"),
            BotCommand(command="bans", description="Проверить блокировки"),
            BotCommand(command="watch", description="Следить за скидкой"),
            BotCommand(command="watchlist", description="Мои уведомления"),
            BotCommand(command="privacy", description="Приватность и удаление"),
            BotCommand(command="help", description="Справка"),
        ]
    )

    timeout = httpx.Timeout(15, connect=10)
    limits = httpx.Limits(max_connections=20, max_keepalive_connections=10)
    async with httpx.AsyncClient(timeout=timeout, limits=limits, follow_redirects=True) as http:
        steam = SteamClient(settings.steam_api_key, http)
        store = SteamStoreClient(http, settings.price_country, settings.price_language)
        await bot.delete_webhook(drop_pending_updates=False)
        logger.info("Bot started in long-polling mode")
        try:
            await dispatcher.start_polling(bot, steam=steam, store=store)
        finally:
            await bot.session.close()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
