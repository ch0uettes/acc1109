from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Callable, Mapping, Optional

from app.balance.constraint_engine.result import ConstraintPipeline, ConstraintResult

AggregationFn = Callable[[list[ConstraintResult]], float]


def _sum_penalty_and_heuristic(results: list[ConstraintResult]) -> float:
    return sum(r.penalty + r.heuristic_score for r in results)


@dataclass(frozen=True)
class SearchGuidanceSummary:
    """Full breakdown of how a branch's search-guidance score was
    computed, not just the number - which pipeline contributed what, and
    how the Strategy Modifier factored in - so ExplainableAI / Decision
    Log / Statistics can show *why* a branch was prioritized. Only
    `.total_score` is used as the actual sort key by ConstraintExecutor;
    everything else is carried purely for explainability."""

    pipeline_scores: Mapping[ConstraintPipeline, float]
    strategy_modifier: float
    total_score: float


class SearchGuidanceAggregator:
    """Turns {pipeline: [ConstraintResult, ...]} into one SearchGuidanceSummary.
    Every pipeline defaults to `sum` (penalty + heuristic_score) unless
    overridden - e.g. a future config might set RELATIONSHIP -> max (one
    bad relationship dominates rather than averaging out), PREFERENCE ->
    a weighted sum, SEARCH_GUIDANCE -> average. No pipeline needs a
    non-default strategy yet; the override point exists so adding one is
    a constructor arg here, never a code change in ConstraintExecutor."""

    def __init__(self, aggregation_by_pipeline: Optional[dict[ConstraintPipeline, AggregationFn]] = None) -> None:
        self._aggregation_by_pipeline = aggregation_by_pipeline or {}

    def aggregate(
        self,
        results_by_pipeline: dict[ConstraintPipeline, list[ConstraintResult]],
        strategy_modifier: float = 0.0,
    ) -> SearchGuidanceSummary:
        pipeline_scores: dict[ConstraintPipeline, float] = {}
        for pipeline, results in results_by_pipeline.items():
            aggregation_fn = self._aggregation_by_pipeline.get(pipeline, _sum_penalty_and_heuristic)
            pipeline_scores[pipeline] = aggregation_fn(results) if results else 0.0
        total_score = sum(pipeline_scores.values()) + strategy_modifier
        return SearchGuidanceSummary(
            pipeline_scores=MappingProxyType(pipeline_scores),
            strategy_modifier=strategy_modifier,
            total_score=total_score,
        )


DEFAULT_SEARCH_GUIDANCE_AGGREGATOR = SearchGuidanceAggregator()
