from __future__ import annotations

from app.balance.constraint_engine.base import PartialHardConstraint
from app.balance.constraint_engine.context import ConstraintContext
from app.balance.constraint_engine.registry import ConstraintRegistry
from app.balance.constraint_engine.result import ConstraintPipeline, ConstraintResult, ConstraintStatus
from app.balance.search_engine import BacktrackingSearchEngine
from app.models.player import Player
from app.position.preference_manager import RolePreferenceManager
from app.utils.enums import Position, Tier


def _player(pid: int, rating: float) -> Player:
    return Player(id=pid, nickname=f"p{pid}", tier=Tier.GOLD, main_role=Position.MID, official_rating=rating)


def _preferences(players):
    manager = RolePreferenceManager()
    return {p.id: manager.resolve(p) for p in players}


def _make_separation_constraint(forbidden_pair: frozenset):
    """Test-double PartialHardConstraint: two specific players may never
    share a team - the canonical monotonic partial rule (once both are
    seated together, adding more players never un-violates it)."""

    class _SeparationTestDouble(PartialHardConstraint):
        name = "test_separation"
        pipeline = ConstraintPipeline.RELATIONSHIP
        default_priority = 80
        description = "test double - forbidden_pair must never share a team"

        def evaluate(self, context: ConstraintContext) -> ConstraintResult:
            this_id = context.candidate_player.id
            if this_id not in forbidden_pair:
                return ConstraintResult(
                    constraint_name=self.name, pipeline=self.pipeline, tier=self.tier, status=ConstraintStatus.PASS
                )
            roster_ids = {p.id for p in context.rosters[context.team_index]}
            violated = bool((forbidden_pair - {this_id}) & roster_ids)
            return ConstraintResult(
                constraint_name=self.name, pipeline=self.pipeline, tier=self.tier,
                status=ConstraintStatus.FAIL if violated else ConstraintStatus.PASS,
                prune=violated,
            )

    return _SeparationTestDouble


def test_partial_hard_pruning_prevents_forbidden_pair_from_sharing_a_team():
    players = [_player(i, 1000 + i * 37) for i in range(10)]
    forbidden_pair = frozenset({players[0].id, players[1].id})
    registry = ConstraintRegistry()
    registry.register(_make_separation_constraint(forbidden_pair))

    engine = BacktrackingSearchEngine(max_nodes=2000, time_budget_seconds=3.0, constraint_registry=registry)
    results = engine.search_top_k(players, _preferences(players), k=5)

    assert len(results) >= 1
    for result in results:
        for team in result.teams:
            team_ids = {p.id for p in team.players}
            assert not forbidden_pair.issubset(team_ids)


def test_partial_hard_pruning_increments_pruned_branch_count():
    players = [_player(i, 1000 + i * 37) for i in range(10)]
    forbidden_pair = frozenset({players[0].id, players[1].id})
    registry = ConstraintRegistry()
    registry.register(_make_separation_constraint(forbidden_pair))

    engine = BacktrackingSearchEngine(max_nodes=2000, time_budget_seconds=3.0, constraint_registry=registry)
    engine.search_top_k(players, _preferences(players), k=5)

    assert engine.last_constraint_statistics.pruned_branch_count > 0


def test_empty_registry_never_prunes():
    players = [_player(i, 1000 + i * 37) for i in range(10)]
    engine = BacktrackingSearchEngine(max_nodes=500, time_budget_seconds=2.0)
    engine.search_top_k(players, _preferences(players), k=3)

    assert engine.last_constraint_statistics.pruned_branch_count == 0
