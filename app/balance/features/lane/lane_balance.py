from __future__ import annotations

from app.balance.config import DEFAULT_NORMALIZATION_CONFIG, NormalizationConfig
from app.balance.features.base import FeaturePriority, IBalanceFeature
from app.balance.features.scaling import LinearNormalizer
from app.models.team import Team
from app.utils.enums import Position


class LaneBalanceFeature(IBalanceFeature):
    """Per-lane rating gap across teams, independent of overall average -
    both teams' TOP should be close, both MIDs should be close, etc.
    Generalizes to N teams via max()-min() per lane, summed across all 5
    lanes. Requires Team.slots.

    Normalized via a Threshold-style linear ramp (raw / lane_difference_max,
    clipped to 1.0) - lane-by-lane fairness is the "라인전 공정성" signal
    Competitive strategy cares about most directly, so its Normalizer
    stays simple and legible rather than a curve-fit."""

    name = "lane_balance"
    category = "lane"
    description = "라인별 Rating 차이 계산"
    default_enabled = True
    default_weight = 0.35
    priority = FeaturePriority.CRITICAL

    def __init__(self, config: NormalizationConfig = DEFAULT_NORMALIZATION_CONFIG) -> None:
        self._normalizer = LinearNormalizer(config.lane_difference_max)

    def evaluate_raw(self, teams: list[Team]) -> float:
        if any(team.slots is None for team in teams):
            raise ValueError("LaneBalanceFeature requires Team.slots (position-aware pipeline only)")
        total = 0.0
        for position in Position:
            ratings = []
            for team in teams:
                slot = next((s for s in team.slots if s.position == position), None)
                if slot is not None:
                    ratings.append(slot.player.final_rating)
            if len(ratings) >= 2:
                total += max(ratings) - min(ratings)
        return total

    def normalize(self, raw: float) -> float:
        return self._normalizer(raw)
