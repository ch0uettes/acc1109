from __future__ import annotations

from app.balance.config import HardConstraintConfig, NormalizationConfig
from app.balance.constraints import HardConstraintLayer
from app.balance.result import BalanceResult
from app.balance.search_engine import BacktrackingSearchEngine, TeamSearchEngine
from app.models.player import Player
from app.position.preference_manager import RolePreferenceManager
from app.utils.enums import Position, Tier
from app.utils.exceptions import InvalidPlayerCountError

import pytest


def _players(count: int, ratings=None) -> list[Player]:
    ratings = ratings or [1000 + i * 37 for i in range(count)]
    roles = list(Position)
    return [
        Player(
            id=i + 1,
            nickname=f"p{i}",
            tier=Tier.GOLD,
            main_role=roles[i % len(roles)],
            official_rating=ratings[i],
        )
        for i in range(count)
    ]


def _preferences(players: list[Player]) -> dict:
    manager = RolePreferenceManager()
    return {p.id: manager.resolve(p) for p in players}


def test_rejects_player_count_not_multiple_of_five():
    engine = BacktrackingSearchEngine(max_nodes=10)
    players = _players(3)
    with pytest.raises(InvalidPlayerCountError):
        engine.search(players, _preferences(players))


def test_every_player_placed_once_with_five_distinct_lanes_per_team():
    engine = BacktrackingSearchEngine(max_nodes=50, time_budget_seconds=2.0)
    players = _players(10)
    result = engine.search(players, _preferences(players))

    assert len(result.teams) == 2
    all_ids = []
    for team in result.teams:
        assert team.slots is not None
        assert {s.position for s in team.slots} == set(Position)
        all_ids.extend(s.player.id for s in team.slots)
    assert sorted(all_ids) == sorted(p.id for p in players)


def test_hard_constraint_respected_end_to_end():
    # A single team of 5 with all-distinct Main roles has exactly one
    # possible "split" (everyone on one team), so this isolates
    # PositionAssigner's hard constraint end-to-end through the search
    # engine without the multi-team rating trade-offs confounding it -
    # the evaluator has no other split to prefer, so it must land on the
    # zero-penalty assignment.
    engine = BacktrackingSearchEngine(max_nodes=50, time_budget_seconds=2.0)
    players = _players(5)
    result = engine.search(players, _preferences(players))

    for team in result.teams:
        assert all(s.role_source != "other" for s in team.slots)
        assert all(s.role_penalty == 0.0 for s in team.slots)


def test_tiny_node_budget_still_returns_valid_result_via_warm_start():
    engine = BacktrackingSearchEngine(max_nodes=0, time_budget_seconds=2.0)
    players = _players(10)
    result = engine.search(players, _preferences(players))

    assert len(result.teams) == 2
    all_ids = [s.player.id for team in result.teams for s in team.slots]
    assert sorted(all_ids) == sorted(p.id for p in players)


def test_search_is_deterministic():
    engine = BacktrackingSearchEngine(max_nodes=50, time_budget_seconds=2.0)
    players = _players(10)
    preferences = _preferences(players)

    first = engine.search(players, preferences)
    second = engine.search(players, preferences)

    first_layout = [sorted(s.player.id for s in team.slots) for team in first.teams]
    second_layout = [sorted(s.player.id for s in team.slots) for team in second.teams]
    assert first_layout == second_layout
    assert first.cost == second.cost


def _team_signature(result: BalanceResult) -> frozenset:
    return frozenset(frozenset(p.id for p in team.players) for team in result.teams)


def test_search_top_k_returns_k_distinct_results_sorted_by_cost():
    engine = BacktrackingSearchEngine(max_nodes=2000, time_budget_seconds=3.0)
    players = _players(20)
    results = engine.search_top_k(players, _preferences(players), k=3)

    assert len(results) == 3
    costs = [r.cost for r in results]
    assert costs == sorted(costs)
    signatures = {_team_signature(r) for r in results}
    assert len(signatures) == 3  # no duplicate team-membership combinations


def test_search_top_k_best_result_matches_plain_search():
    engine = BacktrackingSearchEngine(max_nodes=2000, time_budget_seconds=3.0)
    players = _players(10)
    preferences = _preferences(players)

    top = engine.search_top_k(players, preferences, k=3)
    single = engine.search(players, preferences)

    assert top[0].cost == single.cost


def test_search_top_k_gracefully_returns_fewer_than_k_when_not_enough_distinct_splits_exist():
    # Exactly one team (5 players) has exactly one possible "split".
    engine = BacktrackingSearchEngine(max_nodes=200, time_budget_seconds=2.0)
    players = _players(5)
    results = engine.search_top_k(players, _preferences(players), k=3)
    assert len(results) == 1


def test_custom_normalization_config_actually_changes_reported_cost():
    # Proves normalization_config threads all the way through
    # FeatureRegistry.get_active_features() into the Features actually
    # run, not just stored unused on the engine.
    players = _players(10)
    preferences = _preferences(players)

    default_engine = BacktrackingSearchEngine(max_nodes=50, time_budget_seconds=2.0)
    default_result = default_engine.search(players, preferences)

    tight_config = NormalizationConfig(average_rating_midpoint=1.0, average_rating_steepness=1.0)
    custom_engine = BacktrackingSearchEngine(
        max_nodes=50, time_budget_seconds=2.0, normalization_config=tight_config
    )
    custom_result = custom_engine.search(players, preferences)

    assert custom_result.cost != default_result.cost


def test_hard_constraint_layer_falls_back_to_warm_start_when_nothing_satisfies_it():
    # An operator-configured threshold so strict nothing in the explored
    # space satisfies it still must return a valid result (the warm-start
    # guarantee - see BacktrackingSearchEngine's docstring).
    players = _players(10)
    preferences = _preferences(players)
    impossible = HardConstraintLayer(HardConstraintConfig(average_rating_diff_max=-1.0))
    engine = BacktrackingSearchEngine(max_nodes=50, time_budget_seconds=2.0, hard_constraints=impossible)

    result = engine.search(players, preferences)

    assert len(result.teams) == 2
    all_ids = [p.id for team in result.teams for p in team.players]
    assert sorted(all_ids) == sorted(p.id for p in players)


def test_search_normalizes_cost_to_a_bounded_range_regardless_of_rating_scale():
    # Regression test for the raw-Feature-scale-dominance bug: before
    # normalizing each Feature to [0, 1] across the candidate pool before
    # weighting, team_variance's squared-rating-point values (tens of
    # thousands) swamped average_rating's linear ones (hundreds) no
    # matter what the Strategy's weight table said, so `cost` could run
    # into the thousands. Weights sum to ~1.0 per Strategy, so a properly
    # normalized cost must stay in a small bounded range even when raw
    # player ratings span a huge gap (100 to 3700 here).
    engine = BacktrackingSearchEngine(max_nodes=500, time_budget_seconds=2.0)
    players = _players(10, ratings=[100, 500, 900, 1300, 1700, 2100, 2500, 2900, 3300, 3700])
    result = engine.search(players, _preferences(players))
    assert result.cost <= 1.5


def test_team_search_engine_default_search_top_k_wraps_plain_search():
    class _SingleResultEngine(TeamSearchEngine):
        def __init__(self, result: BalanceResult) -> None:
            self._result = result

        def search(self, players, preferences) -> BalanceResult:
            return self._result

    engine = BacktrackingSearchEngine(max_nodes=50, time_budget_seconds=2.0)
    players = _players(10)
    expected = engine.search(players, _preferences(players))

    fallback_engine = _SingleResultEngine(expected)
    assert fallback_engine.search_top_k(players, _preferences(players), k=3) == [expected]
