from __future__ import annotations

from app.balance.config import DEFAULT_NORMALIZATION_CONFIG, NormalizationConfig
from app.balance.features.base import FeaturePriority, IBalanceFeature
from app.balance.features.scaling import PiecewiseNormalizer
from app.models.team import Team
from app.utils.enums import Tier


class TierDistributionFeature(IBalanceFeature):
    """Penalizes teams having a different *count* of players in each Riot
    tier, even when overall averages already match - e.g. "both teams
    have 2 Diamond+ players" is a distinct fairness signal from "both
    teams average 1800 rating" (one team could be 5 mid-Platinums, the
    other 1 Diamond carry + 4 weak Golds averaging the same).

    Normalized via a hand-tuned Piecewise curve rather than a formula -
    "how bad" a tier-count gap is doesn't scale smoothly (a gap of 1 is
    barely noticeable; a gap of 3+ is a very different team feel), so a
    few explicit (raw, score) breakpoints fit better than any single
    curve shape."""

    name = "tier_distribution"
    category = "team"
    description = "티어 분포 유사도 계산"
    default_enabled = True
    default_weight = 0.20
    priority = FeaturePriority.HIGH

    def __init__(self, config: NormalizationConfig = DEFAULT_NORMALIZATION_CONFIG) -> None:
        self._normalizer = PiecewiseNormalizer(list(config.tier_distribution_breakpoints))

    def evaluate_raw(self, teams: list[Team]) -> float:
        total = 0.0
        for tier in Tier:
            counts = [sum(1 for p in team.players if p.tier == tier) for team in teams]
            total += max(counts) - min(counts)
        return total

    def normalize(self, raw: float) -> float:
        return self._normalizer(raw)
