from __future__ import annotations

import math

from app.balance.config import DEFAULT_NORMALIZATION_CONFIG, NormalizationConfig
from app.balance.features.base import FeaturePriority, IBalanceFeature
from app.balance.features.scaling import LinearNormalizer
from app.models.team import Team
from app.utils.enums import Position


class LaneBalanceFeature(IBalanceFeature):
    """Per-lane rating gap across teams, independent of overall average -
    both teams' TOP should be close, both MIDs should be close, etc.
    Generalizes to N teams via max()-min() per lane. Requires Team.slots.

    Combined across lanes via RMS (root-mean-square), not a plain sum -
    a single catastrophically-mismatched lane (e.g. TOP off by 1000)
    should score much worse than the same total gap spread evenly
    across all 5 lanes (e.g. every lane off by 200 - same sum, 1080 vs
    1100, but a real 1000-point lane mismatch decides the game far more
    than 5 mild ones do). Squaring the per-lane gaps before averaging is
    what makes the one-bad-lane case dominate instead of washing out
    into a similar-looking total.

    Normalized via a Threshold-style linear ramp (raw / lane_difference_max,
    clipped to 1.0) - lane-by-lane fairness is the "라인전 공정성" signal
    Competitive strategy cares about most directly, so its Normalizer
    stays simple and legible rather than a curve-fit."""

    name = "lane_balance"
    category = "lane"
    description = "라인별 Rating 차이 (RMS - 한 라인의 극단적 격차를 강하게 반영)"
    default_enabled = True
    default_weight = 0.20
    priority = FeaturePriority.CRITICAL

    def __init__(self, config: NormalizationConfig = DEFAULT_NORMALIZATION_CONFIG) -> None:
        self._normalizer = LinearNormalizer(config.lane_difference_max)

    def evaluate_raw(self, teams: list[Team]) -> float:
        if any(team.slots is None for team in teams):
            raise ValueError("LaneBalanceFeature requires Team.slots (position-aware pipeline only)")
        squared_gaps = []
        for position in Position:
            ratings = []
            for team in teams:
                slot = next((s for s in team.slots if s.position == position), None)
                if slot is not None:
                    ratings.append(slot.player.final_rating)
            if len(ratings) >= 2:
                gap = max(ratings) - min(ratings)
                squared_gaps.append(gap * gap)
        if not squared_gaps:
            return 0.0
        return math.sqrt(sum(squared_gaps) / len(squared_gaps))

    def normalize(self, raw: float) -> float:
        return self._normalizer(raw)
