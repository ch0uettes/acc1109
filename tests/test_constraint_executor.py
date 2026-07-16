from __future__ import annotations

from types import MappingProxyType

import pytest

from app.balance.balancer import TeamBalancer
from app.balance.constraint_engine.base import LeafHardConstraint, PartialHardConstraint, SoftConstraint
from app.balance.constraint_engine.context import ConstraintContext
from app.balance.constraint_engine.context_factory import ConstraintContextFactory
from app.balance.constraint_engine.executor import ConstraintExecutor
from app.balance.constraint_engine.registry import ConstraintRegistry
from app.balance.constraint_engine.result import ConstraintPipeline, ConstraintResult, ConstraintStatus, ConstraintTier
from app.balance.search_engine import BacktrackingSearchEngine
from app.balance.strategy import StableStrategy
from app.balance.search_policy import StableSearchPolicy
from app.models.player import Player
from app.models.team import Team, TeamSlot
from app.position.preference_manager import RolePreferenceManager
from app.position.signup import PlayerSignup
from app.utils.enums import Position, Tier


def _player(pid: int, nickname: str = "p") -> Player:
    return Player(id=pid, nickname=f"{nickname}{pid}", tier=Tier.GOLD, main_role=Position.MID, official_rating=1000)


class _AlwaysPassPartial(PartialHardConstraint):
    name = "always_pass_partial"
    pipeline = ConstraintPipeline.RELATIONSHIP
    default_priority = 50
    description = "test double - never prunes"

    def evaluate(self, context: ConstraintContext) -> ConstraintResult:
        return ConstraintResult(
            constraint_name=self.name, pipeline=self.pipeline, tier=self.tier, status=ConstraintStatus.PASS
        )


class _AlwaysPrune(PartialHardConstraint):
    name = "always_prune"
    pipeline = ConstraintPipeline.RELATIONSHIP
    default_priority = 90
    description = "test double - always prunes"

    def evaluate(self, context: ConstraintContext) -> ConstraintResult:
        return ConstraintResult(
            constraint_name=self.name, pipeline=self.pipeline, tier=self.tier, status=ConstraintStatus.FAIL, prune=True
        )


class _AlwaysFailLeaf(LeafHardConstraint):
    name = "always_fail_leaf"
    pipeline = ConstraintPipeline.STRUCTURAL
    default_priority = 100
    description = "test double - always fails at leaf"

    def evaluate(self, context: ConstraintContext) -> ConstraintResult:
        return ConstraintResult(
            constraint_name=self.name, pipeline=self.pipeline, tier=self.tier, status=ConstraintStatus.FAIL
        )


class _FixedPenaltySoft(SoftConstraint):
    name = "fixed_penalty_soft"
    pipeline = ConstraintPipeline.SEARCH_GUIDANCE
    default_priority = 10
    description = "test double - always returns penalty=1.0"

    def evaluate(self, context: ConstraintContext) -> ConstraintResult:
        return ConstraintResult(
            constraint_name=self.name, pipeline=self.pipeline, tier=self.tier, status=ConstraintStatus.PASS, penalty=1.0
        )


def _executor(registry: ConstraintRegistry) -> ConstraintExecutor:
    return ConstraintExecutor(registry=registry, strategy=StableStrategy(), search_policy=StableSearchPolicy())


def test_registry_active_sorts_by_priority_descending():
    registry = ConstraintRegistry()
    registry.register(_AlwaysPassPartial)
    registry.register(_AlwaysPrune)
    active = registry.active(ConstraintTier.PARTIAL_HARD)
    assert [c.name for c in active] == ["always_prune", "always_pass_partial"]


def test_registry_active_filters_by_pipeline():
    registry = ConstraintRegistry()
    registry.register(_AlwaysPassPartial)
    registry.register(_AlwaysFailLeaf)
    assert [c.name for c in registry.active(ConstraintTier.PARTIAL_HARD, pipeline=ConstraintPipeline.STRUCTURAL)] == []
    assert [c.name for c in registry.active(ConstraintTier.LEAF_HARD, pipeline=ConstraintPipeline.STRUCTURAL)] == [
        "always_fail_leaf"
    ]


def test_registry_priority_override_changes_order():
    registry = ConstraintRegistry()
    registry.register(_AlwaysPassPartial)  # default_priority=50
    registry.register(_AlwaysPrune)  # default_priority=90
    active = registry.active(ConstraintTier.PARTIAL_HARD, priority_overrides={"always_pass_partial": 999})
    assert [c.name for c in active] == ["always_pass_partial", "always_prune"]


def test_executor_evaluate_partial_prunes_and_stops_after_first_prune():
    registry = ConstraintRegistry()
    registry.register(_AlwaysPrune)
    registry.register(_AlwaysPassPartial)
    executor = _executor(registry)
    players = [_player(1)]
    results = executor.evaluate_partial([[], []], 0, players[0], players, {})
    assert len(results) == 1  # short-circuited, second constraint never ran
    assert results[0].prune is True
    assert executor.statistics().pruned_branch_count == 1


def test_executor_evaluate_partial_empty_registry_is_noop():
    executor = _executor(ConstraintRegistry())
    players = [_player(1)]
    results = executor.evaluate_partial([[], []], 0, players[0], players, {})
    assert results == []
    assert executor.statistics().pruned_branch_count == 0


def test_executor_evaluate_leaf_tracks_hard_fail_count():
    registry = ConstraintRegistry()
    registry.register(_AlwaysFailLeaf)
    executor = _executor(registry)
    players = [_player(i) for i in range(5)]
    results = executor.evaluate_leaf([], players, {})
    assert results[0].status == ConstraintStatus.FAIL
    assert executor.statistics().hard_fail_count == 1


def test_executor_compute_search_guidance_sums_soft_penalty():
    registry = ConstraintRegistry()
    registry.register(_FixedPenaltySoft)
    executor = _executor(registry)
    players = [_player(1)]
    guidance = executor.compute_search_guidance([[], []], [0, 1], players[0], players, {})
    assert guidance[0].total_score == pytest.approx(1.0)
    assert guidance[1].total_score == pytest.approx(1.0)
    assert executor.statistics().soft_penalty_total == pytest.approx(2.0)


def test_executor_priority_resolution_strategy_overrides_server_overrides_default():
    class _StrategyWithOverride(StableStrategy):
        def constraint_priority_overrides(self):
            return {"always_pass_partial": 5}

    registry = ConstraintRegistry()
    registry.register(_AlwaysPassPartial)  # default_priority=50
    executor = ConstraintExecutor(
        registry=registry,
        strategy=_StrategyWithOverride(),
        search_policy=StableSearchPolicy(),
        constraint_priorities={"always_pass_partial": 999},  # server override - should lose to strategy
    )
    assert executor._effective_priorities["always_pass_partial"] == 5


def test_context_fields_are_immutable():
    players = (_player(1),)
    context = ConstraintContext(
        rosters=((), ()),
        team_index=0,
        candidate_player=players[0],
        teams=None,
        player_profiles=players,
        role_preferences=MappingProxyType({}),
        strategy=StableStrategy(),
        search_policy=StableSearchPolicy(),
        constraint_priorities=MappingProxyType({}),
    )
    with pytest.raises((AttributeError, TypeError)):
        context.rosters[0].append(players[0])  # tuple has no .append - fails immediately
    with pytest.raises(TypeError):
        context.role_preferences["x"] = None  # MappingProxyType is read-only


def test_constraint_result_metadata_is_immutable():
    result = ConstraintResult(
        constraint_name="x", pipeline=ConstraintPipeline.STRUCTURAL, tier=ConstraintTier.LEAF_HARD,
        status=ConstraintStatus.PASS, metadata=MappingProxyType({"a": 1}),
    )
    with pytest.raises(TypeError):
        result.metadata["b"] = 2


def test_context_factory_deep_copies_players_so_plugin_mutation_cant_leak_into_live_search():
    live_player = _player(1, "live")
    factory = ConstraintContextFactory()

    partial_context = factory.create_partial_context(
        rosters=[[live_player], []], team_index=0, player=live_player,
        player_profiles=[live_player], role_preferences={}, strategy=StableStrategy(),
        search_policy=StableSearchPolicy(),
    )
    partial_context.candidate_player.tier = Tier.MASTER
    assert live_player.tier == Tier.GOLD  # the live object handed in is untouched

    slot = TeamSlot(position=Position.MID, player=live_player, role_penalty=0.0, role_source="main")
    live_team = Team(index=0, players=[live_player], slots=[slot])
    leaf_context = factory.create_leaf_context(
        teams=[live_team], player_profiles=[live_player], role_preferences={},
        strategy=StableStrategy(), search_policy=StableSearchPolicy(),
    )
    leaf_context.teams[0].players.append(_player(2, "intruder"))
    leaf_context.teams[0].slots[0].player.nickname = "tampered"
    assert len(live_team.players) == 1  # the live Team's own roster is untouched
    assert live_team.slots[0].player.nickname == "live1"  # the live Player is untouched


def test_resolve_defaults_to_hard_enforcing_a_match_override():
    from app.position.schemas import RolePreference
    from app.utils.enums import Position

    players = [_player(i) for i in range(5)]
    signups = [PlayerSignup(player=players[0], match_override=RolePreference(main=Position.SUPPORT))] + [
        PlayerSignup(player=p) for p in players[1:]
    ]
    _, _, override_player_ids = TeamBalancer()._resolve(signups)
    assert override_player_ids == frozenset({players[0].id})


def test_resolve_leaves_override_soft_when_enforce_fixed_role_is_false():
    from app.position.schemas import RolePreference
    from app.utils.enums import Position

    players = [_player(i) for i in range(5)]
    signups = [
        PlayerSignup(
            player=players[0], match_override=RolePreference(main=Position.SUPPORT), enforce_fixed_role=False
        )
    ] + [PlayerSignup(player=p) for p in players[1:]]
    _, preferences, override_player_ids = TeamBalancer()._resolve(signups)
    assert override_player_ids == frozenset()  # not hard-enforced
    assert preferences[players[0].id].main == Position.SUPPORT  # still used as a soft preference


def test_backtracking_search_engine_forwards_constraint_priorities_to_executor():
    engine = BacktrackingSearchEngine(constraint_priorities={"fixed_role": 999})
    players = [_player(i) for i in range(5)]
    manager = RolePreferenceManager()
    preferences = {p.id: manager.resolve(p) for p in players}
    engine.search_top_k(players, preferences, k=1)
    assert engine.constraint_executor._effective_priorities["fixed_role"] == 999


def test_team_balancer_forwards_server_constraint_priorities_end_to_end():
    players = [_player(i) for i in range(5)]
    signups = [PlayerSignup(player=p) for p in players]
    balancer = TeamBalancer(constraint_priorities={"fixed_role": 777})
    balancer.run(signups, k=1)
    assert balancer.search_engine.constraint_executor._effective_priorities["fixed_role"] == 777
