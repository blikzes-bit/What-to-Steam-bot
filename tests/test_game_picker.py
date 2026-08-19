import random

import pytest

from app.db.repositories import CommonGame
from app.services.game_picker import pick_candidates, select_winner


def game(app_id: int, minutes: int) -> CommonGame:
    return CommonGame(app_id=app_id, name=f"Game {app_id}", total_playtime=minutes)


def test_pick_candidates_returns_three_unique_games() -> None:
    result = pick_candidates([game(index, index * 10) for index in range(20)], rng=random.Random(7))

    assert len(result) == 3
    assert len({item.app_id for item in result}) == 3
    assert all(item.app_id < 15 for item in result)


def test_pick_candidates_handles_small_library() -> None:
    games = [game(1, 10), game(2, 20)]

    assert {item.app_id for item in pick_candidates(games, rng=random.Random(1))} == {1, 2}


def test_select_winner_uses_highest_vote_count() -> None:
    assert select_winner([("A", 1), ("B", 3), ("C", 2)], rng=random.Random(1)) == "B"


def test_select_winner_rejects_empty_list() -> None:
    with pytest.raises(ValueError):
        select_winner([])
