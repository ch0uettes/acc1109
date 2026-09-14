from __future__ import annotations

from app.balance.config import HardConstraintConfig, NormalizationConfig
from app.balance.constraints import HardConstraintLayer
from app.balance.result import BalanceResult
from app.balance.search_engine import BacktrackingSearchEngine, TeamSearchEngine, _filter_by_quality
from app.models.player import Player
from app.position.preference_manager import RolePreferenceManager
from app.position.schemas import RolePreference
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


def test_search_top_k_returns_distinct_results_sorted_by_cost():
    # Up to k, not always exactly k - _filter_by_quality can legitimately
    # drop a distinct-but-far-worse alternative (see the quality-gate
    # tests below), so this only asserts what's returned is sorted and
    # non-duplicate, not an exact count.
    engine = BacktrackingSearchEngine(max_nodes=2000, time_budget_seconds=3.0)
    players = _players(20)
    results = engine.search_top_k(players, _preferences(players), k=3)

    assert 1 <= len(results) <= 3
    costs = [r.cost for r in results]
    assert costs == sorted(costs)
    signatures = {_team_signature(r) for r in results}
    assert len(signatures) == len(results)  # no duplicate team-membership combinations


def test_search_populates_feature_contributions_for_returned_results():
    # explain() is only computed for the final returned results, not
    # every leaf visited - verify it actually lands on BalanceResult.
    engine = BacktrackingSearchEngine(max_nodes=200, time_budget_seconds=2.0)
    players = _players(10)
    result = engine.search(players, _preferences(players))

    assert len(result.contributions) > 0
    names = {c.name for c in result.contributions}
    assert names == set(result.cost_breakdown.keys())
    total_contribution = sum(c.contribution for c in result.contributions)
    assert total_contribution == pytest.approx(result.cost)


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

    tight_config = NormalizationConfig(mean_balance_midpoint=1.0, mean_balance_steepness=1.0)
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
    impossible = HardConstraintLayer(HardConstraintConfig(mean_balance_diff_max=-1.0))
    engine = BacktrackingSearchEngine(max_nodes=50, time_budget_seconds=2.0, hard_constraints=impossible)

    result = engine.search(players, preferences)

    assert len(result.teams) == 2
    all_ids = [p.id for team in result.teams for p in team.players]
    assert sorted(all_ids) == sorted(p.id for p in players)


# --- _filter_by_quality: 2위/3위가 1위보다 지나치게 나쁘면 아예 보여주지
# 않는다 (극단적으로 불균형한 조합이 "대안"처럼 보이는 걸 방지). ---


def test_filter_by_quality_drops_alternatives_far_worse_than_the_best():
    good = BalanceResult(teams=[], cost=0.1)
    ok = BalanceResult(teams=[], cost=0.15)
    bad = BalanceResult(teams=[], cost=1.0)
    assert _filter_by_quality([good, ok, bad], max_cost_ratio=2.0) == [good, ok]


def test_filter_by_quality_keeps_everything_within_the_ratio():
    a = BalanceResult(teams=[], cost=0.2)
    b = BalanceResult(teams=[], cost=0.3)
    c = BalanceResult(teams=[], cost=0.35)
    assert _filter_by_quality([a, b, c], max_cost_ratio=2.0) == [a, b, c]


def test_filter_by_quality_handles_zero_best_cost():
    zero_a = BalanceResult(teams=[], cost=0.0)
    zero_b = BalanceResult(teams=[], cost=0.0)
    nonzero = BalanceResult(teams=[], cost=0.1)
    assert _filter_by_quality([zero_a, zero_b, nonzero], max_cost_ratio=2.0) == [zero_a, zero_b]


def test_search_top_k_drops_far_worse_combos_for_a_skewed_roster():
    # Mirrors the real-world case that motivated this: a few very-high
    # outliers plus a tightly clustered rest. Once the search moves past
    # the one well-balanced split, remaining distinct partitions can be
    # dramatically worse - those must not be presented as "2위/3위"
    # alongside a much better 1위. max_cost_ratio defaults to 1.25.
    ratings = [3000, 2950, 2900, 2850, 2800] + [500 + i * 5 for i in range(15)]
    players = _players(20, ratings=ratings)
    engine = BacktrackingSearchEngine(max_nodes=3000, time_budget_seconds=3.0)

    results = engine.search_top_k(players, _preferences(players), k=3)

    assert len(results) >= 1
    best_cost = results[0].cost
    for extra in results[1:]:
        assert extra.cost <= best_cost * engine.max_cost_ratio


def test_search_normalizes_cost_to_a_bounded_range_regardless_of_rating_scale():
    # Regression test for the raw-Feature-scale-dominance bug: before
    # normalizing each Feature to [0, 1] across the candidate pool before
    # weighting, team_variance's squared-rating-point values (tens of
    # thousands) swamped mean_balance's linear ones (hundreds) no
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


def test_warm_start_fallback_records_hard_fail_count_once_not_twice():
    """Regression test: search_top_k() re-derived last_constraint_results by
    calling evaluate_leaf() a second time on each returned result, on the
    very same (stateful) ConstraintExecutor already used during the search
    - double-counting ConstraintStatistics.hard_fail_count for any result
    that failed hard constraints (observable whenever the warm-start
    fallback kicks in, since that result necessarily failed during the
    search). Every genuine evaluate_leaf() call during the search happens
    exactly once per DFS leaf reached (one per last_nodes_expanded
    increment) plus once for the warm start - so with every leaf forced to
    fail (3 players fixed to the same TOP role, only 1 TOP slot per team),
    hard_fail_count must equal exactly that count, not more."""
    players = _players(10)
    preferences = _preferences(players)
    forced_ids = frozenset({players[0].id, players[1].id, players[2].id})
    for pid in forced_ids:
        preferences[pid] = RolePreference(main=Position.TOP)

    engine = BacktrackingSearchEngine(max_nodes=50, time_budget_seconds=1.0)
    results = engine.search_top_k(players, preferences, k=3, override_player_ids=forced_ids)

    assert len(results) == 1  # the warm-start fallback, nothing else qualified
    genuine_evaluation_count = engine.last_nodes_expanded + 1  # +1 for the warm start
    assert engine.last_constraint_statistics.hard_fail_count == genuine_evaluation_count


def test_partial_hard_pruning_lets_the_search_actually_satisfy_multiple_fixed_roles():
    """Regression test: before FixedRoleCollisionConstraint existed, the
    DFS had no way to know mid-search that seating two hard-forced players
    into the same forced position on one roster is fatal - it only found
    out at the leaf, after a complete team was already built. With several
    forced players in a larger lobby, that meant the search could burn its
    entire default node budget on doomed leaves and silently fall back to
    a warm-start result that violates the operator's pin just as badly
    (see the class docstring: the warm start guarantees *a* valid result,
    never that every Hard Constraint is met under a budget). Pruning a
    colliding branch before recursing into it means the budget is spent
    only on leaves that can actually satisfy every forced player - with 6
    teams and only 4 forced players here, that's always possible."""
    players = _players(30)
    preferences = _preferences(players)
    forced_ids = frozenset(p.id for p in players[:4])
    for pid in forced_ids:
        preferences[pid] = RolePreference(main=Position.JUNGLE)

    engine = BacktrackingSearchEngine()  # production defaults: max_nodes=20_000, time_budget=5.0
    results = engine.search_top_k(players, preferences, k=1, override_player_ids=forced_ids)

    assert engine.last_constraint_statistics.pruned_branch_count > 0
    best = results[0]
    forced_slots = [
        slot for team in best.teams for slot in (team.slots or []) if slot.player.id in forced_ids
    ]
    assert len(forced_slots) == len(forced_ids)
    assert all(slot.position == Position.JUNGLE for slot in forced_slots)
    assert all(slot.role_source == "main" for slot in forced_slots)
