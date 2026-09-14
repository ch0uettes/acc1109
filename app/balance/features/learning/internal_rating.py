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

    Each team's mean is a *confidence-weighted* average of internal_rating
    (sum(rating*confidence) / sum(confidence)), not a plain mean of
    confidence_weighted_internal_rating() values - a brand-new player's
    barely-tested Internal Rating should count for less than a veteran's
    well-established one, but a plain mean of rating*confidence instead
    drags the whole team's number toward zero in proportion to how many
    low-confidence players it has, even when their actual rating is
    identical to a high-confidence teammate's. That conflates "how much to
    trust this data" with "how strong this team is," which is exactly the
    thing confidence_weighted_internal_rating()'s modifier role is
    supposed to avoid - see app.balance.features.learning.modifiers.

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
        means = [self._confidence_weighted_team_mean(team) for team in teams]
        return max(means) - min(means)

    @staticmethod
    def _confidence_weighted_team_mean(team: Team) -> float:
        total_confidence = sum(p.confidence for p in team.players)
        if total_confidence <= 0:
            return statistics.fmean(p.internal_rating for p in team.players)
        return sum(confidence_weighted_internal_rating(p) for p in team.players) / total_confidence

    def normalize(self, raw: float) -> float:
        return self._normalizer(raw)
