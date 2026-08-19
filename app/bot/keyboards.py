from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


class LobbyAction(CallbackData, prefix="lobby"):
    lobby_id: int
    action: str


class LobbyVote(CallbackData, prefix="vote"):
    lobby_id: int
    candidate_id: int


def lobby_open_keyboard(lobby_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Я играю",
                    callback_data=LobbyAction(lobby_id=lobby_id, action="join").pack(),
                ),
                InlineKeyboardButton(
                    text="➖ Выйти",
                    callback_data=LobbyAction(lobby_id=lobby_id, action="leave").pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🎲 Подобрать игры",
                    callback_data=LobbyAction(lobby_id=lobby_id, action="pick").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="✖️ Отменить",
                    callback_data=LobbyAction(lobby_id=lobby_id, action="cancel").pack(),
                )
            ],
        ]
    )


def voting_keyboard(lobby_id: int, candidates: list[tuple[int, str, int]]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"{position}. {name[:35]}",
                callback_data=LobbyVote(lobby_id=lobby_id, candidate_id=candidate_id).pack(),
            )
        ]
        for position, (candidate_id, name, _votes) in enumerate(candidates, start=1)
    ]
    rows.append(
        [
            InlineKeyboardButton(
                text="🏁 Завершить голосование",
                callback_data=LobbyAction(lobby_id=lobby_id, action="finish").pack(),
            )
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text="✖️ Отменить",
                callback_data=LobbyAction(lobby_id=lobby_id, action="cancel").pack(),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)
