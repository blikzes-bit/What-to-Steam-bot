import pytest

from app.bot.handlers import parse_app_id


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("730", 730),
        ("https://store.steampowered.com/app/730/CounterStrike_2/", 730),
        ("invalid", None),
    ],
)
def test_parse_app_id(value: str, expected: int | None) -> None:
    assert parse_app_id(value) == expected
