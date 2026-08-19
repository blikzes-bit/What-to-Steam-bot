import asyncio
import logging

import httpx
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from app.bot.handlers import router
from app.bot.middleware import DbSessionMiddleware
from app.clients.steam import SteamClient
from app.clients.store import SteamStoreClient
from app.core.config import get_settings
from app.core.logging import configure_logging

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
    dispatcher.include_router(router)

    await bot.set_my_commands(
        [
            BotCommand(command="link", description="Привязать Steam-профиль"),
            BotCommand(command="profile", description="Мой Steam-профиль"),
            BotCommand(command="sync", description="Обновить библиотеку"),
            BotCommand(command="lobby", description="Собрать игровое лобби"),
            BotCommand(command="common", description="Общие игры группы"),
            BotCommand(command="online", description="Кто сейчас играет"),
            BotCommand(command="watch", description="Следить за скидкой"),
            BotCommand(command="watchlist", description="Мои уведомления"),
            BotCommand(command="help", description="Справка"),
        ]
    )

    timeout = httpx.Timeout(15, connect=10)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as http:
        steam = SteamClient(settings.steam_api_key, http)
        store = SteamStoreClient(http, settings.price_country, settings.price_language)
        await bot.delete_webhook(drop_pending_updates=False)
        logger.info("Bot started in long-polling mode")
        try:
            await dispatcher.start_polling(bot, steam=steam, store=store)
        finally:
            await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
