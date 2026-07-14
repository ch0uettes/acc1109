from __future__ import annotations

import statistics

from app.balance.config import DEFAULT_NORMALIZATION_CONFIG, NormalizationConfig
from app.balance.features.base import FeaturePriority, IBalanceFeature
from app.balance.features.scaling import LogarithmicNormalizer
from app.models.team import Team


class InterTeamBalanceFeature(IBalanceFeature):
    """Variance (not standard deviation) of every team's average Rating -
    squaring each team's deviation from the global mean means a single
    team sitting way off the mean gets punished much harder than the
    same total gap spread evenly across teams. This is what should
    dominate whenever any one team ends up radically stronger/weaker
    than the rest (the "one stacked team" failure mode), complementing
    AverageRatingFeature's stddev-based, more linearly-scaled read on
    typical spread.

    Normalized Logarithmically (like TeamVarianceFeature) since variance
    is a squared-rating-point unit with a huge dynamic range."""

    name = "inter_team_balance"
    category = "team"
    description = "팀 평균 Rating들의 팀-간 분산 (한 팀이라도 크게 벗어나면 크게 페널티)"
    default_enabled = True
    default_weight = 0.30
    priority = FeaturePriority.CRITICAL

    def __init__(self, config: NormalizationConfig = DEFAULT_NORMALIZATION_CONFIG) -> None:
        self._normalizer = LogarithmicNormalizer(config.inter_team_balance_scale)

    def evaluate_raw(self, teams: list[Team]) -> float:
        means = [team.average_rating for team in teams]
        return statistics.pvariance(means)

    def normalize(self, raw: float) -> float:
        return self._normalizer(raw)
