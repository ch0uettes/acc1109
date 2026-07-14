from __future__ import annotations

from app.models.player import Player
from app.rating.base import RatingCalculator


class FinalRatingCalculator:
    """Combines official + internal rating. Weights default to 1.0 (a plain
    sum) but are already parameterized for the future weighting scheme."""

    def __init__(
        self,
        official: RatingCalculator,
        internal: RatingCalculator,
        official_weight: float = 1.0,
        internal_weight: float = 1.0,
    ) -> None:
        self.official = official
        self.internal = internal
        self.official_weight = official_weight
        self.internal_weight = internal_weight

    def calculate(self, player: Player) -> float:
        return (
            self.official_weight * self.official.calculate(player)
            + self.internal_weight * self.internal.calculate(player)
        )
