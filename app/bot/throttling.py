import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject


class ThrottlingMiddleware(BaseMiddleware):
    def __init__(self, message_interval: float = 0.8, callback_interval: float = 0.35) -> None:
        self.message_interval = message_interval
        self.callback_interval = callback_interval
        self._last_seen: dict[tuple[int, str], float] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, (Message, CallbackQuery)) or not event.from_user:
            return await handler(event, data)

        now = time.monotonic()
        event_type = "callback" if isinstance(event, CallbackQuery) else "message"
        key = (event.from_user.id, event_type)
        interval = self.callback_interval if event_type == "callback" else self.message_interval
        previous = self._last_seen.get(key)
        if previous is not None and now - previous < interval:
            if isinstance(event, CallbackQuery):
                await event.answer("Слишком быстро — попробуйте ещё раз через секунду")
            return None
        self._last_seen[key] = now

        if len(self._last_seen) > 10_000:
            cutoff = now - 3600
            self._last_seen = {
                stored_key: timestamp
                for stored_key, timestamp in self._last_seen.items()
                if timestamp >= cutoff
            }
        return await handler(event, data)
