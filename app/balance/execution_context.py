from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from app.balance.config import HardConstraintConfig, NormalizationConfig
from app.balance.result import BalanceResult, FeatureContribution
from app.balance.search_policy import SearchPolicy
from app.balance.strategy import IBalanceStrategy
from app.models.player import Player
from app.position.schemas import RolePreference

"""One AI run's data container, threaded through PlayerEvaluation ->
SearchEngine -> BalanceEvaluator -> ExplainableAI -> DecisionLogger so
those stages exchange information only through this object, never by
calling into each other directly or by growing an ever-longer parameter
list. Every dataclass here is frozen (immutable) and pure data - no
method does any calculation, scoring, or Feature evaluation; that logic
lives entirely in the modules that build these objects (TeamBalancer,
BacktrackingSearchEngine, ExplainableAI, ...). A stage that needs to
"write" its result does so by building a NEW ExecutionContext via
dataclasses.replace(), never by mutating the one it was handed - see
TeamBalancer.run() for the only place these get chained together.

Split into three sections so this never grows into one God Object as
more stages (Constraint Engine, AI Learning Engine, Discord Bot, ...)
start reading/writing it:

- InputContext: everything known BEFORE the search runs (who's playing,
  which Strategy/SearchPolicy/config, version info). Never changes once
  built.
- RuntimeContext: everything the search/evaluation stages produce (the
  candidates themselves, feasibility results, Feature snapshots, search
  stats). feature_snapshots is the single source of truth for Feature
  results - every other stage (ExplainableAI, DecisionLogger, future
  Learning Engine/Debug UI) reads from here instead of recomputing or
  keeping its own copy.
- ResultContext: everything the explain/log stages produce (the final
  recommendation list, human-facing explain data, which one got chosen,
  the persisted Decision Log id)."""


@dataclass(frozen=True)
class SearchStatistics:
    nodes_expanded: int
    elapsed_seconds: float
    candidate_count: int
    node_budget_hit: bool
    time_budget_hit: bool


@dataclass(frozen=True)
class VersionMetadata:
    app_version: str
    strategy_name: str
    search_policy_name: str
    feature_weights: dict[str, float]


@dataclass(frozen=True)
class ConstraintResult:
    candidate_index: int
    feasible: bool
    violations: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ExplainData:
    """Human/UI-facing summary derived FROM feature_snapshots (never
    recomputed) - top contributing Features per candidate, in a shape
    ready for display rather than raw per-Feature numbers."""

    top_contributors: dict[int, list[FeatureContribution]]  # candidate_index -> top-N by |contribution|


@dataclass(frozen=True)
class InputContext:
    execution_id: str
    started_at: datetime
    strategy: IBalanceStrategy
    search_policy: SearchPolicy
    normalization_config: NormalizationConfig
    hard_constraint_config: HardConstraintConfig
    player_profiles: list[Player]
    role_preferences: dict[int, RolePreference]
    version_metadata: VersionMetadata


@dataclass(frozen=True)
class RuntimeContext:
    candidate_teams: list[BalanceResult] = field(default_factory=list)
    constraint_results: list[ConstraintResult] = field(default_factory=list)
    feature_snapshots: dict[int, list[FeatureContribution]] = field(default_factory=dict)
    search_statistics: Optional[SearchStatistics] = None
    finished_at: Optional[datetime] = None


@dataclass(frozen=True)
class ResultContext:
    top_recommendations: list[BalanceResult] = field(default_factory=list)
    explain_data: Optional[ExplainData] = None
    final_selection: Optional[int] = None
    decision_log_id: Optional[int] = None


@dataclass(frozen=True)
class ExecutionContext:
    input: InputContext
    runtime: RuntimeContext = field(default_factory=RuntimeContext)
    result: ResultContext = field(default_factory=ResultContext)
