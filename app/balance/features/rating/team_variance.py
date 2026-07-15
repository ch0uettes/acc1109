from __future__ import annotations

import statistics

from app.balance.config import DEFAULT_NORMALIZATION_CONFIG, NormalizationConfig
from app.balance.features.base import FeaturePriority, IBalanceFeature
from app.balance.features.scaling import LogarithmicNormalizer
from app.models.team import Team


class TeamVarianceFeature(IBalanceFeature):
    """Responsibility: 팀 내부 안정성 - is any one team's own roster a
    single carry + four weak players (Master/Diamond/Gold/Silver/Bronze
    all crammed together), regardless of how that team's average
    compares to any other team's. Deliberately never "are the teams'
    averages close to each other" - that question belongs entirely to
    MeanBalanceFeature/OutlierPenaltyFeature. This Feature must never be
    weighted so heavily that it rewards clustering similar-rated players
    onto the same team purely to shrink each team's own internal spread,
    since that can widen the cross-team average gap those other two
    Features are responsible for catching (a Strategy's weight table
    should keep this below the combined weight of the cross-team
    Features).

    Normalized via a Logarithmic curve, not linearly - pvariance's raw
    unit is squared rating points, so its dynamic range dwarfs every
    other Feature's (tens to hundreds of thousands vs hundreds/thousands
    elsewhere). A log scale compresses that range so this Feature's
    weight actually reflects the Strategy's intent instead of the raw
    unit swamping everything else after weighting."""

    name = "team_variance"
    category = "rating"
    description = "팀 내부 안정성 (팀 간 평균 격차는 담당하지 않음)"
    default_enabled = True
    default_weight = 0.12
    priority = FeaturePriority.MEDIUM

    def __init__(self, config: NormalizationConfig = DEFAULT_NORMALIZATION_CONFIG) -> None:
        self._normalizer = LogarithmicNormalizer(config.team_variance_scale)

    def evaluate_raw(self, teams: list[Team]) -> float:
        # Per-team variance, then averaged across teams (not a max-min
        # gap between teams' variances) - a single team with wildly
        # mixed tiers should be penalized on its own, regardless of
        # whether every OTHER team happens to be equally messy.
        variances = [
            statistics.pvariance([p.final_rating for p in team.players])
            for team in teams
        ]
        return statistics.fmean(variances)

    def normalize(self, raw: float) -> float:
        return self._normalizer(raw)
