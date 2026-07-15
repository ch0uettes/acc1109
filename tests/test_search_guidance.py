from __future__ import annotations

from app.balance.constraint_engine.base import SoftConstraint
from app.balance.constraint_engine.context import ConstraintContext
from app.balance.constraint_engine.registry import ConstraintRegistry
from app.balance.constraint_engine.result import ConstraintPipeline, ConstraintResult, ConstraintStatus
from app.balance.search_engine import BacktrackingSearchEngine
from app.balance.search_policy import StableSearchPolicy
from app.models.player import Player
from app.position.preference_manager import RolePreferenceManager
from app.utils.enums import Position, Tier


def _player(pid: int, rating: float) -> Player:
    return Player(id=pid, nickname=f"p{pid}", tier=Tier.GOLD, main_role=Position.MID, official_rating=rating)


def _preferences(players):
    manager = RolePreferenceManager()
    return {p.id: manager.resolve(p) for p in players}


class _PreferTeamZero(SoftConstraint):
    """Test-double: penalizes any team_index != 0, so a stable sort should
    always explore team 0 first for every player."""

    name = "prefer_team_zero"
    pipeline = ConstraintPipeline.SEARCH_GUIDANCE
    default_priority = 10
    description = "test double - penalizes any non-zero team_index"

    def evaluate(self, context: ConstraintContext) -> ConstraintResult:
        penalty = 0.0 if context.team_index == 0 else 100.0
        return ConstraintResult(
            constraint_name=self.name, pipeline=self.pipeline, tier=self.tier,
            status=ConstraintStatus.PASS, penalty=penalty,
        )


class _RecordingOrderPolicy(StableSearchPolicy):
    """Records the candidate_team_indices order it's handed by
    branch_priority(), proving Search Guidance ran (and reordered) before
    SearchPolicy got final say."""

    name = "recording"

    def __init__(self) -> None:
        self.seen_orders: list[list[int]] = []

    def branch_priority(self, player, candidate_team_indices, rosters):
        self.seen_orders.append(list(candidate_team_indices))
        return super().branch_priority(player, candidate_team_indices, rosters)


def test_search_guidance_reorders_candidates_before_branch_priority_runs():
    players = [_player(i, 1000 + i * 37) for i in range(10)]
    registry = ConstraintRegistry()
    registry.register(_PreferTeamZero)
    policy = _RecordingOrderPolicy()

    engine = BacktrackingSearchEngine(
        max_nodes=200, time_budget_seconds=2.0, constraint_registry=registry, search_policy=policy
    )
    engine.search_top_k(players, _preferences(players), k=1)

    # Whenever both teams were still open candidates, team 0 (penalty 0.0)
    # must have been sorted ahead of team 1 (penalty 100.0).
    two_way_orders = [order for order in policy.seen_orders if len(order) == 2]
    assert two_way_orders, "expected at least one branch decision between 2 open teams"
    assert all(order == [0, 1] for order in two_way_orders)


def test_empty_registry_reproduces_stable_order_byte_for_byte():
    players = [_player(i, 1000 + i * 37) for i in range(10)]
    engine_a = BacktrackingSearchEngine(max_nodes=500, time_budget_seconds=2.0)
    engine_b = BacktrackingSearchEngine(max_nodes=500, time_budget_seconds=2.0)

    result_a = engine_a.search(players, _preferences(players))
    result_b = engine_b.search(players, _preferences(players))

    layout_a = [sorted(p.id for p in team.players) for team in result_a.teams]
    layout_b = [sorted(p.id for p in team.players) for team in result_b.teams]
    assert layout_a == layout_b
    assert result_a.cost == result_b.cost
