from datetime import UTC, datetime

import pytest
from aiogram.types import Chat, Message, User

from app.bot.throttling import ThrottlingMiddleware


def make_message() -> Message:
    return Message(
        message_id=1,
        date=datetime.now(UTC),
        chat=Chat(id=10, type="private"),
        from_user=User(id=20, is_bot=False, first_name="Test"),
        text="/start",
    )


@pytest.mark.asyncio
async def test_throttling_drops_rapid_duplicate_messages() -> None:
    calls = 0

    async def handler(_event, _data):
        nonlocal calls
        calls += 1
        return "handled"

    middleware = ThrottlingMiddleware(message_interval=60)
    message = make_message()

    assert await middleware(handler, message, {}) == "handled"
    assert await middleware(handler, message, {}) is None
    assert calls == 1
