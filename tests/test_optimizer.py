from __future__ import annotations

import pytest

from app.balance.features import default_balance_evaluator
from app.balance.optimizer import RandomSwapOptimizer, TieredSnakeDraftOptimizer
from app.models.player import Player
from app.utils.enums import Position, Tier
from app.utils.exceptions import InvalidPlayerCountError


def _players(ratings: list[float]) -> list[Player]:
    return [
        Player(nickname=f"p{i}", tier=Tier.GOLD, main_role=Position.MID, official_rating=r)
        for i, r in enumerate(ratings)
    ]


def test_rejects_player_count_not_multiple_of_five():
    optimizer = RandomSwapOptimizer(seed=1)
    with pytest.raises(InvalidPlayerCountError):
        optimizer.optimize(_players([100, 200, 300]), default_balance_evaluator())


def test_optimizer_lowers_cost_for_skewed_input():
    ratings = [100, 100, 100, 100, 100, 900, 900, 900, 900, 900]
    optimizer = RandomSwapOptimizer(max_iterations=500, random_restarts=5, seed=42)
    result = optimizer.optimize(_players(ratings), default_balance_evaluator())
    assert result.cost < 200


def test_tiered_snake_draft_rejects_player_count_not_multiple_of_five():
    optimizer = TieredSnakeDraftOptimizer()
    with pytest.raises(InvalidPlayerCountError):
        optimizer.optimize(_players([100, 200, 300]), default_balance_evaluator())


def test_tiered_snake_draft_pairs_strongest_with_weakest_on_every_team():
    # Two teams: ranks by rating are 190..100 (10 players, 2 teams of 5) -
    # tier 0 is the top-2 (190, 180), tier 4 is the bottom-2 (110, 100).
    # Every team must get exactly one player from the top tier and one
    # from the bottom tier.
    ratings = [190, 180, 170, 160, 150, 140, 130, 120, 110, 100]
    optimizer = TieredSnakeDraftOptimizer()
    result = optimizer.optimize(_players(ratings), default_balance_evaluator())

    assert len(result.teams) == 2
    for team in result.teams:
        team_ratings = {p.official_rating for p in team.players}
        assert team_ratings & {190, 180}  # has exactly one top-tier player
        assert team_ratings & {110, 100}  # has exactly one bottom-tier player
