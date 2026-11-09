from __future__ import annotations


class FinalRatingBlender:
    """Final Rating = base_rating (Official or Seed) + a share of the
    Internal Rating correction, the share growing as inhouse games
    accumulate: (1 - base_weight) of it, from 10% for a brand-new player to
    70% after `games_to_plateau` games.

    Internal Rating is a relative correction that starts at 0 and can go
    negative (see PlayerService.override_internal_rating), not a score on
    the same scale as base_rating. It used to be averaged with base_rating
    (base * w + internal * (1 - w)), which dragged every player toward 0 as
    their games piled up - a regular with 20 games came out at ~30% of
    their tier score, far below a newcomer of a lower tier. Adding it as a
    correction keeps everyone on the tier scale: no correction, no change.

    Provisional (to be revisited): the weights and the plateau are the old
    blend's, kept as they were.

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
        return base_rating + internal_rating * (1 - self.base_weight(games_played))


DEFAULT_FINAL_RATING_BLENDER = FinalRatingBlender()
