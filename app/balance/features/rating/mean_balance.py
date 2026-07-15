from __future__ import annotations

import statistics

from app.balance.config import DEFAULT_NORMALIZATION_CONFIG, NormalizationConfig
from app.balance.features.base import FeaturePriority, IBalanceFeature
from app.balance.features.scaling import LogisticNormalizer
from app.models.team import Team


class MeanBalanceFeature(IBalanceFeature):
    """Responsibility: how close are ALL teams' averages to the overall
    (global) mean, considered together - "전체적인 평균 균형". This is
    deliberately NOT about the single worst-off team (that's
    OutlierPenaltyFeature's job) and NOT about any one team's internal
    tier spread (TeamVarianceFeature's job) - just "do the team averages
    as a whole sit close together around the mean."

    Computed as the standard deviation of team averages (one reasonable
    choice among RMS/stddev/MAD - the PRD leaves the exact formula open,
    only the responsibility is fixed). Max-min was deliberately rejected
    here: it only looks at the two most extreme teams and is blind to
    how the rest are distributed."""

    name = "mean_balance"
    category = "rating"
    description = "전체 팀 평균의 균형 (Global Mean 대비 표준편차)"
    default_enabled = True
    default_weight = 0.28
    priority = FeaturePriority.CRITICAL

    def __init__(self, config: NormalizationConfig = DEFAULT_NORMALIZATION_CONFIG) -> None:
        self._normalizer = LogisticNormalizer(config.mean_balance_midpoint, config.mean_balance_steepness)

    def evaluate_raw(self, teams: list[Team]) -> float:
        means = [team.average_rating for team in teams]
        return statistics.pstdev(means)

    def normalize(self, raw: float) -> float:
        return self._normalizer(raw)
