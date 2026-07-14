from __future__ import annotations

from app.balance.features.base import IBalanceFeature
from app.balance.strategy import IBalanceStrategy
from app.models.team import Team


class BalanceEvaluator:
    """Pure orchestrator - never knows how many Features exist, which
    ones are enabled, or what any of them weigh, and never normalizes
    anything itself (each Feature owns its own Normalizer - see
    IBalanceFeature). Three separate steps instead of one combined
    evaluate(), matching the pipeline:

        Raw Metric -> Feature Normalizer -> Normalized Score (0~1)
                    -> Strategy Weight -> Weighted Score -> Total

        raw = evaluator.evaluate_raw(teams, features)          # display
        normalized = evaluator.normalize(raw, features)        # ranking input
        cost = evaluator.combine(normalized, strategy)

    Categories, Features, and Strategies never talk to each other
    directly - this is the one place their outputs get combined."""

    def evaluate_raw(self, teams: list[Team], features: list[IBalanceFeature]) -> dict[str, float]:
        return {feature.name: feature.evaluate_raw(teams) for feature in features}

    def normalize(
        self, raw_breakdown: dict[str, float], features: list[IBalanceFeature]
    ) -> dict[str, float]:
        by_name = {feature.name: feature for feature in features}
        return {name: by_name[name].normalize(value) for name, value in raw_breakdown.items()}

    def combine(self, normalized_breakdown: dict[str, float], strategy: IBalanceStrategy) -> float:
        total = 0.0
        for name, value in normalized_breakdown.items():
            weight = strategy.get_weight(name)
            if weight == 0:
                continue
            total += value * weight
        return total
