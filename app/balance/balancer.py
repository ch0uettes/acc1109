from __future__ import annotations

import dataclasses
import time
import uuid
from datetime import datetime

from app.balance.config import DEFAULT_HARD_CONSTRAINT_CONFIG, DEFAULT_NORMALIZATION_CONFIG, NormalizationConfig
from app.balance.constraint_engine.result import ConstraintStatus
from app.balance.constraints import HardConstraintLayer
from app.balance.execution_context import (
    ConstraintResult,
    ConstraintStatistics,
    ExecutionContext,
    InputContext,
    RuntimeContext,
    SearchStatistics,
    VersionMetadata,
)
from app.balance.explainable_ai import ExplainableAI
from app.balance.result import BalanceResult
from app.balance.search_engine import BacktrackingSearchEngine, TeamSearchEngine
from app.balance.search_policy import SEARCH_POLICY_REGISTRY, SearchPolicy, StableSearchPolicy
from app.balance.strategy import DEFAULT_STRATEGY, IBalanceStrategy
from app.position.preference_manager import RolePreferenceManager
from app.position.signup import PlayerSignup
from app.version import APP_VERSION


class TeamBalancer:
    """Entry point services/UI call. Thin orchestrator only: resolves each
    signup's RolePreference (this-match override -> Player Profile) via
    RolePreferenceManager, then delegates the actual team-membership +
    position-assignment search to TeamSearchEngine. No evaluation or
    search logic lives here - see BalanceEvaluator/TeamSearchEngine for
    that, so a Discord Bot/Web/Mobile layer can call this same Core
    Engine without touching Streamlit.

    run() is the primary method: it builds one ExecutionContext per call
    and threads it through PlayerEvaluation (this class's own _resolve())
    -> SearchEngine -> ExplainableAI, returning the finished context.
    generate_teams()/generate_top_teams() are thin backward-compatible
    wrappers over run() that just extract .runtime.candidate_teams, kept
    so every existing BalanceResult-based caller (save_generated_teams,
    team_page.py, tests) needs zero changes."""

    def __init__(
        self,
        search_engine: TeamSearchEngine | None = None,
        preference_manager: RolePreferenceManager | None = None,
        strategy: IBalanceStrategy | None = None,
        normalization_config: NormalizationConfig | None = None,
        hard_constraints: HardConstraintLayer | None = None,
        explainable_ai: ExplainableAI | None = None,
    ) -> None:
        """`strategy`/`normalization_config`/`hard_constraints` only apply
        when `search_engine` isn't supplied directly - they're forwarded
        straight to BacktrackingSearchEngine's own default construction,
        so TeamBalancer itself never touches Feature or evaluator
        internals. `normalization_config`/`hard_constraints` are
        typically a Server's saved override (see app/models/server.py).
        Kept as this class's own attributes too (not just forwarded) so
        run() can describe them in ExecutionContext even when a fully
        custom `search_engine` is supplied and doesn't expose them the
        same way BacktrackingSearchEngine does."""
        self.strategy = strategy or DEFAULT_STRATEGY
        self.normalization_config = normalization_config or DEFAULT_NORMALIZATION_CONFIG
        self.hard_constraints = hard_constraints or HardConstraintLayer()
        self.search_engine = search_engine or BacktrackingSearchEngine(
            strategy=self.strategy,
            normalization_config=self.normalization_config,
            hard_constraints=self.hard_constraints,
        )
        self.preference_manager = preference_manager or RolePreferenceManager()
        self.explainable_ai = explainable_ai or ExplainableAI()

    def generate_teams(self, signups: list[PlayerSignup]) -> BalanceResult:
        return self.run(signups, k=1).runtime.candidate_teams[0]

    def generate_top_teams(self, signups: list[PlayerSignup], k: int = 3) -> list[BalanceResult]:
        """Same pipeline as generate_teams(), but returns the best `k`
        distinct team-membership combinations instead of just one - the
        engine explores them in a single pass, no extra search cost."""
        return self.run(signups, k=k).runtime.candidate_teams

    def run(self, signups: list[PlayerSignup], k: int = 3) -> ExecutionContext:
        players, preferences, override_player_ids = self._resolve(signups)

        strategy = getattr(self.search_engine, "strategy", self.strategy)
        search_policy: SearchPolicy = getattr(
            self.search_engine, "search_policy", SEARCH_POLICY_REGISTRY.get(strategy.name, StableSearchPolicy)()
        )
        normalization_config = getattr(self.search_engine, "normalization_config", self.normalization_config)
        hard_constraint_config = getattr(self.hard_constraints, "config", DEFAULT_HARD_CONSTRAINT_CONFIG)

        feature_weights = {
            name: feature_config.weight
            for name, feature_config in strategy.feature_config().items()
            if feature_config.enabled
        }
        input_context = InputContext(
            execution_id=str(uuid.uuid4()),
            started_at=datetime.utcnow(),
            strategy=strategy,
            search_policy=search_policy,
            normalization_config=normalization_config,
            hard_constraint_config=hard_constraint_config,
            player_profiles=players,
            role_preferences=preferences,
            version_metadata=VersionMetadata(
                app_version=APP_VERSION,
                strategy_name=strategy.name,
                search_policy_name=search_policy.name,
                feature_weights=feature_weights,
            ),
        )
        context = ExecutionContext(input=input_context)

        wall_clock_start = time.monotonic()
        candidate_teams = self.search_engine.search_top_k(
            players, preferences, k=k, override_player_ids=override_player_ids
        )
        wall_clock_elapsed = time.monotonic() - wall_clock_start

        # Real per-candidate Constraint Engine results if the search engine
        # exposed them (BacktrackingSearchEngine always does - see
        # last_constraint_results); falls back to a fresh HardConstraintLayer
        # check only for a fully custom TeamSearchEngine that doesn't. This
        # naturally covers whatever search_top_k() actually returned,
        # warm-start fallback included - a Hard-violating fallback result
        # is visible here, not silently treated as compliant.
        leaf_results_per_candidate = getattr(self.search_engine, "last_constraint_results", None)
        constraint_results = [
            ConstraintResult(
                candidate_index=index,
                feasible=(
                    self.hard_constraints.is_feasible(result.teams, result.cost_breakdown)
                    and not any(r.status == ConstraintStatus.FAIL for r in leaf_results)
                ),
                violations=[r.reason for r in leaf_results if r.status == ConstraintStatus.FAIL and r.reason],
            )
            for index, (result, leaf_results) in enumerate(
                zip(
                    candidate_teams,
                    leaf_results_per_candidate or [[] for _ in candidate_teams],
                )
            )
        ]
        constraint_result_details = {
            index: leaf_results for index, leaf_results in enumerate(leaf_results_per_candidate or [])
        }
        feature_snapshots = {index: result.contributions for index, result in enumerate(candidate_teams)}
        search_statistics = SearchStatistics(
            nodes_expanded=getattr(self.search_engine, "last_nodes_expanded", 0),
            elapsed_seconds=getattr(self.search_engine, "last_elapsed_seconds", wall_clock_elapsed),
            candidate_count=len(candidate_teams),
            node_budget_hit=getattr(self.search_engine, "last_node_budget_hit", False),
            time_budget_hit=getattr(self.search_engine, "last_time_budget_hit", False),
        )
        constraint_statistics: ConstraintStatistics | None = getattr(
            self.search_engine, "last_constraint_statistics", None
        )
        runtime_context = RuntimeContext(
            candidate_teams=candidate_teams,
            constraint_results=constraint_results,
            constraint_result_details=constraint_result_details,
            feature_snapshots=feature_snapshots,
            search_statistics=search_statistics,
            constraint_statistics=constraint_statistics,
            finished_at=datetime.utcnow(),
        )
        context = dataclasses.replace(context, runtime=runtime_context)
        return self.explainable_ai.explain(context)

    def _resolve(self, signups: list[PlayerSignup]):
        players = [signup.player for signup in signups]
        preferences = {
            signup.player.id: self.preference_manager.resolve(signup.player, signup.match_override)
            for signup in signups
        }
        # Player ids with an explicit this-match override, as opposed to
        # just their stored profile main/sub role - RolePreferenceManager
        # already collapsed that distinction into `preferences` above, so
        # this has to be captured separately for FixedRoleConstraint (see
        # app/balance/constraint_engine/plugins/role.py) to know which
        # players actually need their position hard-enforced.
        override_player_ids = frozenset(
            signup.player.id for signup in signups if signup.match_override is not None
        )
        return players, preferences, override_player_ids
