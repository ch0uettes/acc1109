from __future__ import annotations


class FinalRatingBlender:
    """Final Rating = base_rating (Official or Seed) blended with
    Internal Rating, with the blend shifting toward Internal Rating as more
    inhouse games accumulate. A brand-new player's Final Rating is almost
    entirely their base rating (we have no inhouse data on them yet); after
    `games_to_plateau` games it's mostly Internal Rating (the project's
    stated end goal is for Internal Rating to become the primary signal).

    The transition is linear between the two weight endpoints - a simple,
    easily-swapped default, not a claim that skill converges linearly."""

    def __init__(
        self,
        initial_base_weight: float = 0.9,
        plateau_base_weight: float = 0.3,
        games_to_plateau: int = 20,
    ) -> None:
        self.initial_base_weight = initial_base_weight
        self.plateau_base_weight = plateau_base_weight
        self.games_to_plateau = games_to_plateau

    def base_weight(self, games_played: int) -> float:
        t = min(games_played / self.games_to_plateau, 1.0) if self.games_to_plateau > 0 else 1.0
        return self.initial_base_weight + (self.plateau_base_weight - self.initial_base_weight) * t

    def blend(self, base_rating: float, internal_rating: float, games_played: int) -> float:
        base_weight = self.base_weight(games_played)
        return base_rating * base_weight + internal_rating * (1 - base_weight)


DEFAULT_FINAL_RATING_BLENDER = FinalRatingBlender()
