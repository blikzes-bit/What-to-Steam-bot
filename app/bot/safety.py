import logging

from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.types import ErrorEvent, InlineKeyboardMarkup, Message

logger = logging.getLogger(__name__)


async def safe_edit_text(
    message: Message,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise


async def handle_unexpected_error(event: ErrorEvent) -> bool:
    logger.error(
        "Unhandled bot update error",
        exc_info=(type(event.exception), event.exception, event.exception.__traceback__),
    )
    try:
        if event.update.callback_query:
            await event.update.callback_query.answer(
                "Что-то пошло не так. Попробуйте ещё раз позже.", show_alert=True
            )
        elif event.update.message:
            await event.update.message.answer(
                "Произошла временная ошибка. Попробуйте ещё раз позже."
            )
    except TelegramAPIError:
        logger.warning("Unable to deliver error message to Telegram", exc_info=True)
    return True
