import asyncio
import html
import logging
from datetime import UTC, datetime

import httpx
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import func, select

from app.clients.store import SteamStoreClient, StoreApiError, StoreOffer
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db import repositories as repo
from app.db.models import User, WatchedGame
from app.db.session import engine, session_factory
from app.services.catalog import select_deals, select_releases

logger = logging.getLogger(__name__)


def format_price(value: int | None, currency: str | None) -> str:
    if value is None:
        return "цена недоступна"
    return f"{value / 100:.2f} {currency or ''}".strip()


async def check_discounts(bot: Bot, store: SteamStoreClient) -> None:
    logger.info("Checking watched Steam discounts")
    async with session_factory() as session:
        lock_acquired = await session.scalar(select(func.pg_try_advisory_xact_lock(764952001)))
        if not lock_acquired:
            logger.info("Another discount worker is already running")
            return
        rows = list(
            (
                await session.execute(
                    select(WatchedGame, User)
                    .join(User, User.id == WatchedGame.user_id)
                    .order_by(WatchedGame.app_id)
                )
            ).tuples()
        )
        offers: dict[int, StoreOffer | None] = {}
        for watched, user in rows:
            if watched.app_id not in offers:
                try:
                    offers[watched.app_id] = await store.get_offer(watched.app_id)
                except StoreApiError:
                    logger.warning("Unable to fetch app %s", watched.app_id, exc_info=True)
                    offers[watched.app_id] = None
            offer = offers[watched.app_id]
            if offer is None:
                continue

            watched.name = offer.name
            watched.last_seen_discount = offer.discount_percent
            watched.last_seen_price = offer.final_price
            watched.currency = offer.currency
            watched.checked_at = datetime.now(UTC)

            qualifies = offer.discount_percent >= watched.threshold_percent
            already_notified = (
                watched.last_notified_discount == offer.discount_percent
                and watched.last_notified_price == offer.final_price
            )
            if qualifies and not already_notified:
                try:
                    store_url = f"https://store.steampowered.com/app/{offer.app_id}"
                    await bot.send_message(
                        user.telegram_id,
                        f"<b>🔥 {html.escape(offer.name)} — скидка {offer.discount_percent}%</b>\n"
                        f"Цена: {format_price(offer.final_price, offer.currency)}\n"
                        f'<a href="{store_url}">Открыть в Steam</a>',
                    )
                except TelegramAPIError:
                    logger.warning(
                        "Unable to notify Telegram user %s", user.telegram_id, exc_info=True
                    )
                else:
                    watched.last_notified_discount = offer.discount_percent
                    watched.last_notified_price = offer.final_price
            elif not qualifies:
                watched.last_notified_discount = None
                watched.last_notified_price = None
        await session.commit()
    logger.info("Discount check finished: %s subscriptions", len(rows))


async def send_daily_digests(bot: Bot, store: SteamStoreClient) -> None:
    today = datetime.now(UTC).date()
    async with session_factory() as session:
        lock_acquired = await session.scalar(select(func.pg_try_advisory_xact_lock(764952002)))
        if not lock_acquired:
            logger.info("Another digest worker is already running")
            return
        recipients = [
            (subscription, user)
            for subscription, user in await repo.get_digest_recipients(session)
            if subscription.last_sent_on != today
        ]
        if not recipients:
            logger.info("No pending digest recipients")
            return
        try:
            catalog = await store.get_featured_catalog()
        except StoreApiError:
            logger.warning("Unable to fetch featured Steam catalog", exc_info=True)
            return

        releases = select_releases(catalog, count=5)
        delivered = 0
        for subscription, user in recipients:
            lines = ["<b>🎮 Ежедневная подборка Steam</b>", ""]
            if subscription.deals_enabled:
                deals = select_deals(catalog, subscription.min_discount, count=6)
                lines.append(f"<b>Скидки от {subscription.min_discount}%</b>")
                if deals:
                    for item in deals:
                        price = format_price(item.final_price, item.currency)
                        lines.append(
                            f'• <a href="https://store.steampowered.com/app/{item.app_id}">'
                            f"{html.escape(item.name)}</a> — {item.discount_percent}%, {price}"
                        )
                else:
                    lines.append("Сегодня подходящих предложений нет.")
                lines.append("")
            if subscription.releases_enabled:
                lines.append("<b>Новые релизы</b>")
                if releases:
                    for item in releases:
                        lines.append(
                            f'• <a href="https://store.steampowered.com/app/{item.app_id}">'
                            f"{html.escape(item.name)}</a>"
                        )
                else:
                    lines.append("Сегодня подборка релизов недоступна.")
                lines.append("")
            lines.append("Настройки: /digest")
            try:
                await bot.send_message(user.telegram_id, "\n".join(lines))
            except TelegramAPIError:
                logger.warning(
                    "Unable to send digest to Telegram user %s",
                    user.telegram_id,
                    exc_info=True,
                )
            else:
                subscription.last_sent_on = today
                delivered += 1
        await session.commit()
    logger.info("Daily digest delivered to %s users", delivered)


async def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    bot = Bot(
        settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML, link_preview_is_disabled=True),
    )
    limits = httpx.Limits(max_connections=10, max_keepalive_connections=5)
    async with httpx.AsyncClient(timeout=20, limits=limits, follow_redirects=True) as http:
        store = SteamStoreClient(http, settings.price_country, settings.price_language)
        scheduler = AsyncIOScheduler(timezone="UTC")
        scheduler.add_job(
            check_discounts,
            "interval",
            minutes=settings.deal_check_interval_minutes,
            args=[bot, store],
            coalesce=True,
            max_instances=1,
            next_run_time=datetime.now(UTC),
        )
        scheduler.add_job(
            send_daily_digests,
            "cron",
            hour=settings.digest_hour_utc,
            minute=0,
            args=[bot, store],
            coalesce=True,
            max_instances=1,
        )
        scheduler.start()
        logger.info("Discount worker started")
        try:
            await asyncio.Event().wait()
        finally:
            scheduler.shutdown(wait=False)
            await bot.session.close()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
