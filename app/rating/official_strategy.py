from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from app.models.player import Player
from app.rating.official import OfficialRatingCalculator, blend_current_and_peak
from app.utils.enums import Tier


class OfficialRatingStrategy(ABC):
    """Computes Official Rating from a player's current-season tier (blended
    with Peak Tier once the two diverge enough - see
    rating.official.blend_current_and_peak). This is the pluggable seam so
    the tier->score formula can evolve without any caller changing. Returns
    None when there is no current-season tier to compute from - callers
    must fall back to an operator-assigned Seed Rating in that case (see
    RatingCaseResolver)."""

    @abstractmethod
    def calculate(self, player: Player) -> Optional[float]:
        ...


class CurrentTierPriorityStrategy(OfficialRatingStrategy):
    def __init__(self, tier_calc: Optional[OfficialRatingCalculator] = None) -> None:
        self.tier_calc = tier_calc or OfficialRatingCalculator()

    def calculate(self, player: Player) -> Optional[float]:
        if player.tier == Tier.UNRANKED:
            return None
        current_score = self.tier_calc.calculate_from(player.tier, player.division, player.lp)
        peak_score = (
            self.tier_calc.calculate_from(player.peak_tier, player.peak_division, player.peak_lp)
            if player.peak_tier is not None and player.peak_division is not None and player.peak_lp is not None
            else None
        )
        return blend_current_and_peak(current_score, peak_score)
