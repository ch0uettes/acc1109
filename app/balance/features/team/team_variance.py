from __future__ import annotations

import statistics

from app.balance.config import DEFAULT_NORMALIZATION_CONFIG, NormalizationConfig
from app.balance.features.base import FeaturePriority, IBalanceFeature
from app.balance.features.scaling import LogarithmicNormalizer
from app.models.team import Team


class TeamVarianceFeature(IBalanceFeature):
    """Gap between teams' *internal* rating spread only - "is one team a
    single carry + four weak players while another is uniformly
    average," never "are the teams' averages close to each other." That
    latter question belongs entirely to AverageRatingFeature/
    InterTeamBalanceFeature - this Feature must never be weighted so
    heavily that it rewards clustering similar-rated players onto the
    same team purely to shrink each team's own internal spread, since
    that can widen the cross-team average gap those other two Features
    are responsible for catching (a Strategy's weight table should keep
    this below the combined weight of the cross-team Features).

    Normalized via a Logarithmic curve, not linearly - pvariance's raw
    unit is squared rating points, so its dynamic range dwarfs every
    other Feature's (tens to hundreds of thousands vs hundreds/thousands
    elsewhere). A log scale compresses that range so this Feature's
    weight actually reflects the Strategy's intent instead of the raw
    unit swamping everything else after weighting."""

    name = "team_variance"
    category = "team"
    description = "팀 내부 Rating 분산 계산 (팀 간 평균 격차는 담당하지 않음)"
    default_enabled = True
    default_weight = 0.10
    priority = FeaturePriority.MEDIUM

    def __init__(self, config: NormalizationConfig = DEFAULT_NORMALIZATION_CONFIG) -> None:
        self._normalizer = LogarithmicNormalizer(config.team_variance_scale)

    def evaluate_raw(self, teams: list[Team]) -> float:
        variances = [
            statistics.pvariance([p.final_rating for p in team.players])
            for team in teams
        ]
        return max(variances) - min(variances)

    def normalize(self, raw: float) -> float:
        return self._normalizer(raw)
