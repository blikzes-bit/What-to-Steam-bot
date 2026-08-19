import random

from app.db.repositories import CommonGame


def pick_candidates(
    games: list[CommonGame], count: int = 3, *, rng: random.Random | None = None
) -> list[CommonGame]:
    """Prefer less overplayed games, then randomly pick from the best pool."""
    if count <= 0 or not games:
        return []
    randomizer = rng or random.Random()
    ranked = sorted(games, key=lambda game: (game.total_playtime, game.name.casefold()))
    pool_size = min(len(ranked), max(count, 15))
    chosen = randomizer.sample(ranked[:pool_size], k=min(count, pool_size))
    return sorted(chosen, key=lambda game: (game.total_playtime, game.name.casefold()))


def select_winner[T](items: list[tuple[T, int]], *, rng: random.Random | None = None) -> T:
    if not items:
        raise ValueError("No candidates")
    max_votes = max(votes for _, votes in items)
    leaders = [item for item, votes in items if votes == max_votes]
    return (rng or random.Random()).choice(leaders)
