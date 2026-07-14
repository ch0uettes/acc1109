from __future__ import annotations

import statistics

from app.balance.config import DEFAULT_NORMALIZATION_CONFIG, NormalizationConfig
from app.balance.features.base import FeaturePriority, IBalanceFeature
from app.balance.features.scaling import LogisticNormalizer
from app.models.team import Team


class AverageRatingFeature(IBalanceFeature):
    """How far each team's average Rating typically strays from the
    overall (global) mean across every team - the standard deviation of
    the team averages, NOT max()-min(). Max-min only looks at the two
    most extreme teams and is blind to how the rest are distributed (a
    3rd/4th team sitting right at the extremes vs. clustered near the
    mean scores identically under max-min, but "feels" very different).
    Standard deviation reflects the whole distribution's spread instead.

    Complementary to InterTeamBalanceFeature, which computes variance
    (not stddev) of the same team averages - squaring deviations makes
    it react far more sharply to a single team sitting way off the mean,
    while this Feature gives the more linearly-interpretable "typical"
    spread in actual rating-point units."""

    name = "average_rating"
    category = "rating"
    description = "팀 평균 Rating의 전체 평균 대비 표준편차 (Max-Min 아님)"
    default_enabled = True
    default_weight = 0.25
    priority = FeaturePriority.CRITICAL

    def __init__(self, config: NormalizationConfig = DEFAULT_NORMALIZATION_CONFIG) -> None:
        self._normalizer = LogisticNormalizer(config.average_rating_midpoint, config.average_rating_steepness)

    def evaluate_raw(self, teams: list[Team]) -> float:
        means = [team.average_rating for team in teams]
        return statistics.pstdev(means)

    def normalize(self, raw: float) -> float:
        return self._normalizer(raw)
