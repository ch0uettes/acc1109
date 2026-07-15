from __future__ import annotations

from app.balance.result import BalanceResult
from app.balance.search_engine import BacktrackingSearchEngine
from app.balance.search_policy import (
    ComfortSearchPolicy,
    CompetitiveSearchPolicy,
    SearchPolicy,
    StableSearchPolicy,
)
from app.balance.strategy import ComfortStrategy, CompetitiveStrategy, StableStrategy
from app.models.player import Player
from app.position.preference_manager import RolePreferenceManager
from app.utils.enums import Position, Tier


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
            recommended_main_role=roles[i % len(roles)],
            recommended_main_confidence=(i % 5) / 5,
        )
        for i in range(count)
    ]


def _preferences(players: list[Player]) -> dict:
    manager = RolePreferenceManager()
    return {p.id: manager.resolve(p) for p in players}


def test_stable_policy_orders_by_rating_descending():
    players = _players(10)
    ordered = StableSearchPolicy().order_players(players)
    assert [p.final_rating for p in ordered] == sorted((p.final_rating for p in players), reverse=True)


def test_competitive_policy_groups_by_main_role():
    players = _players(10)
    ordered = CompetitiveSearchPolicy().order_players(players)
    role_order = list(Position)
    role_indices = [role_order.index(p.main_role) for p in ordered]
    assert role_indices == sorted(role_indices)


def test_comfort_policy_orders_by_recommendation_confidence_descending():
    players = _players(10)
    ordered = ComfortSearchPolicy().order_players(players)
    confidences = [p.recommended_main_confidence or 0.0 for p in ordered]
    assert confidences == sorted(confidences, reverse=True)


def test_default_hooks_are_identity_or_none():
    class _NoOpPolicy(SearchPolicy):
        name = "noop"

        def order_players(self, players):
            return players

    policy = _NoOpPolicy()
    assert policy.warm_start([], 4) is None
    assert policy.branch_priority(None, [0, 1, 2], [[]]) == [0, 1, 2]
    results = [BalanceResult(teams=[], cost=0.5), BalanceResult(teams=[], cost=0.1)]
    assert policy.order_team_candidates(results) == results


def test_hooks_are_actually_invoked_by_the_engine():
    calls = {"order_players": 0, "warm_start": 0, "branch_priority": 0, "order_team_candidates": 0}

    class _RecordingPolicy(StableSearchPolicy):
        name = "recording"

        def order_players(self, players):
            calls["order_players"] += 1
            return super().order_players(players)

        def warm_start(self, ordered_players, num_teams):
            calls["warm_start"] += 1
            return super().warm_start(ordered_players, num_teams)

        def branch_priority(self, player, candidate_team_indices, rosters):
            calls["branch_priority"] += 1
            return super().branch_priority(player, candidate_team_indices, rosters)

        def order_team_candidates(self, results):
            calls["order_team_candidates"] += 1
            return super().order_team_candidates(results)

    engine = BacktrackingSearchEngine(max_nodes=50, time_budget_seconds=2.0, search_policy=_RecordingPolicy())
    players = _players(10)
    engine.search(players, _preferences(players))

    assert calls["order_players"] >= 1
    assert calls["warm_start"] >= 1
    assert calls["branch_priority"] >= 1
    assert calls["order_team_candidates"] >= 1


def test_engine_resolves_search_policy_from_strategy_name_by_default():
    engine = CompetitiveSearchPolicy()  # sanity: importable/instantiable
    assert engine.name == "competitive"

    stable_engine = BacktrackingSearchEngine(strategy=StableStrategy())
    assert isinstance(stable_engine.search_policy, StableSearchPolicy)

    competitive_engine = BacktrackingSearchEngine(strategy=CompetitiveStrategy())
    assert isinstance(competitive_engine.search_policy, CompetitiveSearchPolicy)

    comfort_engine = BacktrackingSearchEngine(strategy=ComfortStrategy())
    assert isinstance(comfort_engine.search_policy, ComfortSearchPolicy)


def test_competitive_and_stable_can_discover_different_candidate_partitions():
    # Not a guarantee for every roster, but for a deliberately mixed
    # 20-player roster with clear role/rating structure, the two
    # policies' different traversal orders should discover a genuinely
    # different best partition within the same node budget - this is
    # the concrete bug SearchPolicy exists to fix (all 3 strategies used
    # to converge on identical candidates).
    ratings = [3000, 2950, 2900, 2850, 2800] + [500 + i * 5 for i in range(15)]
    players = _players(20, ratings=ratings)
    preferences = _preferences(players)

    stable_engine = BacktrackingSearchEngine(
        max_nodes=1500, time_budget_seconds=3.0, strategy=StableStrategy()
    )
    competitive_engine = BacktrackingSearchEngine(
        max_nodes=1500, time_budget_seconds=3.0, strategy=CompetitiveStrategy()
    )

    stable_result = stable_engine.search(players, preferences)
    competitive_result = competitive_engine.search(players, preferences)

    stable_signature = frozenset(frozenset(p.id for p in t.players) for t in stable_result.teams)
    competitive_signature = frozenset(frozenset(p.id for p in t.players) for t in competitive_result.teams)
    assert stable_signature != competitive_signature
