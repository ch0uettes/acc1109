from __future__ import annotations

import time
from typing import Optional

from app.balance.constraint_engine.aggregator import (
    DEFAULT_SEARCH_GUIDANCE_AGGREGATOR,
    SearchGuidanceAggregator,
    SearchGuidanceSummary,
)
from app.balance.constraint_engine.context_factory import (
    DEFAULT_CONSTRAINT_CONTEXT_FACTORY,
    ConstraintContextFactory,
)
from app.balance.constraint_engine.registry import DEFAULT_CONSTRAINT_REGISTRY, ConstraintRegistry
from app.balance.constraint_engine.result import ConstraintPipeline, ConstraintResult, ConstraintTier
from app.balance.search_policy import SearchPolicy
from app.balance.strategy import IBalanceStrategy
from app.models.player import Player
from app.models.team import Team
from app.position.schemas import RolePreference


class ConstraintExecutor:
    """The only interface BacktrackingSearchEngine talks to for
    constraint-related decisions - it never touches ConstraintRegistry,
    ConstraintContextFactory, SearchGuidanceAggregator, or a plugin
    directly. Orchestrates; does not implement context-building
    (delegated to context_factory) or score aggregation (delegated to
    aggregator) itself.

    Resolves each tier's active plugin list ONCE per construction (i.e.
    once per search_top_k() call, since a fresh ConstraintExecutor is
    built per search) rather than per DFS node - the difference between
    near-zero overhead and measurably slowing down the hottest path in
    the codebase when a tier's registry is empty, which it mostly is."""

    def __init__(
        self,
        registry: ConstraintRegistry = DEFAULT_CONSTRAINT_REGISTRY,
        strategy: Optional[IBalanceStrategy] = None,
        search_policy: Optional[SearchPolicy] = None,
        constraint_priorities: Optional[dict[str, int]] = None,
        context_factory: ConstraintContextFactory = DEFAULT_CONSTRAINT_CONTEXT_FACTORY,
        aggregator: SearchGuidanceAggregator = DEFAULT_SEARCH_GUIDANCE_AGGREGATOR,
    ) -> None:
        self.registry = registry
        self.strategy = strategy
        self.search_policy = search_policy
        self.constraint_priorities = constraint_priorities or {}
        self.context_factory = context_factory
        self.aggregator = aggregator

        # Priority resolution: Strategy override > Server override > plugin default.
        strategy_overrides = strategy.constraint_priority_overrides() if strategy is not None else {}
        self._effective_priorities = {**self.constraint_priorities, **strategy_overrides}

        self._active_partial_hard = self.registry.active(ConstraintTier.PARTIAL_HARD, priority_overrides=self._effective_priorities)
        self._active_leaf_hard = self.registry.active(ConstraintTier.LEAF_HARD, priority_overrides=self._effective_priorities)
        self._active_soft = self.registry.active(ConstraintTier.SOFT, priority_overrides=self._effective_priorities)
        self._active_preference = self.registry.active(ConstraintTier.PREFERENCE, priority_overrides=self._effective_priorities)

        self._hard_fail_count = 0
        self._pruned_branch_count = 0
        self._soft_penalty_total = 0.0
        self._preference_penalty_total = 0.0
        self._start_time = time.monotonic()

    def evaluate_partial(
        self,
        rosters: list[list[Player]],
        team_index: int,
        player: Player,
        player_profiles: list[Player],
        role_preferences: dict[int, RolePreference],
    ) -> list[ConstraintResult]:
        if not self._active_partial_hard:
            return []
        context = self.context_factory.create_partial_context(
            rosters, team_index, player, player_profiles, role_preferences,
            self.strategy, self.search_policy, self._effective_priorities,
        )
        results: list[ConstraintResult] = []
        for constraint in self._active_partial_hard:
            result = constraint.evaluate(context)
            results.append(result)
            if result.prune:
                self._pruned_branch_count += 1
                break
        return results

    def evaluate_leaf(
        self,
        teams: list[Team],
        player_profiles: list[Player],
        role_preferences: dict[int, RolePreference],
        override_player_ids: frozenset = frozenset(),
    ) -> list[ConstraintResult]:
        if not self._active_leaf_hard:
            return []
        context = self.context_factory.create_leaf_context(
            teams, player_profiles, role_preferences, self.strategy, self.search_policy, self._effective_priorities,
            override_player_ids=override_player_ids,
        )
        results = [constraint.evaluate(context) for constraint in self._active_leaf_hard]
        if any(r.status.value == "fail" for r in results):
            self._hard_fail_count += 1
        return results

    def compute_search_guidance(
        self,
        rosters: list[list[Player]],
        candidate_team_indices: list[int],
        player: Player,
        player_profiles: list[Player],
        role_preferences: dict[int, RolePreference],
    ) -> dict[int, SearchGuidanceSummary]:
        if not self._active_soft and not self._active_preference:
            return {}
        strategy_modifier = 0.0
        guidance: dict[int, SearchGuidanceSummary] = {}
        for team_index in candidate_team_indices:
            context = self.context_factory.create_partial_context(
                rosters, team_index, player, player_profiles, role_preferences,
                self.strategy, self.search_policy, self._effective_priorities,
            )
            soft_results = [c.evaluate(context) for c in self._active_soft]
            preference_results = [c.evaluate(context) for c in self._active_preference]
            self._soft_penalty_total += sum(r.penalty for r in soft_results)
            self._preference_penalty_total += sum(r.penalty for r in preference_results)
            results_by_pipeline: dict[ConstraintPipeline, list[ConstraintResult]] = {}
            for result in soft_results + preference_results:
                results_by_pipeline.setdefault(result.pipeline, []).append(result)
            guidance[team_index] = self.aggregator.aggregate(results_by_pipeline, strategy_modifier)
        return guidance

    def statistics(self) -> "ConstraintStatistics":
        from app.balance.execution_context import ConstraintStatistics

        return ConstraintStatistics(
            hard_fail_count=self._hard_fail_count,
            soft_penalty_total=self._soft_penalty_total,
            preference_penalty_total=self._preference_penalty_total,
            pruned_branch_count=self._pruned_branch_count,
            execution_time_seconds=time.monotonic() - self._start_time,
        )
