from __future__ import annotations

import statistics

from app.balance.config import DEFAULT_NORMALIZATION_CONFIG, NormalizationConfig
from app.balance.features.base import FeaturePriority, IBalanceFeature
from app.balance.features.scaling import LogarithmicNormalizer
from app.models.team import Team


class TeamVarianceFeature(IBalanceFeature):
    """Gap between teams' internal rating spread, so one team isn't
    'one carry + four weak' while the other is all-average - preferred
    even when both teams' averages are identical.

    Normalized via a Logarithmic curve, not linearly - pvariance's raw
    unit is squared rating points, so its dynamic range dwarfs every
    other Feature's (tens to hundreds of thousands vs hundreds/thousands
    elsewhere). A log scale compresses that range so this Feature's
    weight actually reflects the Strategy's intent instead of the raw
    unit swamping everything else after weighting."""

    name = "team_variance"
    category = "team"
    description = "팀 내부 Rating 분산 계산"
    default_enabled = True
    default_weight = 0.25
    priority = FeaturePriority.HIGH

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
