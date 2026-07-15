from __future__ import annotations

import statistics

from app.balance.config import DEFAULT_NORMALIZATION_CONFIG, NormalizationConfig
from app.balance.features.base import FeaturePriority, IBalanceFeature
from app.balance.features.learning.modifiers import confidence_weighted_internal_rating
from app.balance.features.scaling import LogisticNormalizer
from app.models.team import Team


class InternalRatingFeature(IBalanceFeature):
    """Gap between teams' average *Internal* Rating specifically - the
    inhouse-earned signal (see rating.updater.ExpectedPerformanceUpdateStrategy),
    as opposed to AverageRatingFeature's `final_rating` (which already
    blends Internal with Official/Seed Rating). Isolating it lets a
    Strategy weight "how this community's own games rate someone"
    independently of their Riot-verified rank.

    Each player's contribution is confidence_weighted_internal_rating()
    (internal_rating * confidence), not raw internal_rating - a brand-new
    player's barely-tested Internal Rating counts for less than a
    veteran's well-established one. This is a Confidence *modifier*, not
    an independent ConfidenceFeature scoring its own points - see
    app.balance.features.learning.modifiers for why.

    Normalized via the same Logistic shape as AverageRatingFeature, since
    it shares the same linear rating-point unit."""

    name = "internal_rating"
    category = "learning"
    description = "내전 전용 Internal Rating 격차 계산 (Confidence로 보정)"
    default_enabled = True
    default_weight = 0.15
    priority = FeaturePriority.HIGH

    def __init__(self, config: NormalizationConfig = DEFAULT_NORMALIZATION_CONFIG) -> None:
        self._normalizer = LogisticNormalizer(
            config.internal_rating_midpoint, config.internal_rating_steepness
        )

    def evaluate_raw(self, teams: list[Team]) -> float:
        means = [
            statistics.fmean(confidence_weighted_internal_rating(p) for p in team.players)
            for team in teams
        ]
        return max(means) - min(means)

    def normalize(self, raw: float) -> float:
        return self._normalizer(raw)
