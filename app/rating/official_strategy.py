from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from app.models.player import Player
from app.rating.official import OfficialRatingCalculator
from app.utils.enums import Tier


class OfficialRatingStrategy(ABC):
    """Computes Official Rating from a player's current-season tier. This
    is the pluggable seam so the tier->score formula can evolve (e.g. a
    non-linear scale) without any caller changing. Returns None when there
    is no current-season tier to compute from - callers must fall back to
    an operator-assigned Seed Rating in that case (see RatingCaseResolver),
    never derive Official Rating from Peak Tier."""

    @abstractmethod
    def calculate(self, player: Player) -> Optional[float]:
        ...


class CurrentTierPriorityStrategy(OfficialRatingStrategy):
    def __init__(self, tier_calc: Optional[OfficialRatingCalculator] = None) -> None:
        self.tier_calc = tier_calc or OfficialRatingCalculator()

    def calculate(self, player: Player) -> Optional[float]:
        if player.tier == Tier.UNRANKED:
            return None
        return self.tier_calc.calculate_from(player.tier, player.division, player.lp)
