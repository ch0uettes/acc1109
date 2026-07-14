from __future__ import annotations

from app.models.player import Player
from app.rating.base import RatingCalculator


class InternalRatingCalculator(RatingCalculator):
    """Reads the accumulated inhouse-only rating stored on the player.
    Actual adjustments after a match are handled by rating.updater."""

    def calculate(self, player: Player) -> float:
        return player.internal_rating
