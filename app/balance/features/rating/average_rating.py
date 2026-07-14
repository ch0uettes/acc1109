from __future__ import annotations

from app.balance.config import DEFAULT_NORMALIZATION_CONFIG, NormalizationConfig
from app.balance.features.base import FeaturePriority, IBalanceFeature
from app.balance.features.scaling import LogisticNormalizer
from app.models.team import Team


class AverageRatingFeature(IBalanceFeature):
    """Gap between the strongest and weakest team's average final rating.

    Normalized via a Logistic curve (not a hard threshold) - a gap of
    399 vs 401 should score almost identically, which a hard cutoff
    can't guarantee but a smooth sigmoid does by construction."""

    name = "average_rating"
    category = "rating"
    description = "팀 평균 Rating 차이 계산"
    default_enabled = True
    default_weight = 0.20
    priority = FeaturePriority.HIGH

    def __init__(self, config: NormalizationConfig = DEFAULT_NORMALIZATION_CONFIG) -> None:
        self._normalizer = LogisticNormalizer(config.average_rating_midpoint, config.average_rating_steepness)

    def evaluate_raw(self, teams: list[Team]) -> float:
        means = [team.average_rating for team in teams]
        return max(means) - min(means)

    def normalize(self, raw: float) -> float:
        return self._normalizer(raw)
