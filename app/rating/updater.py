from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.models.player import Player

# Once a calibration player has played this many matches, their Internal
# Rating swings should settle back to normal - the whole point of
# Calibration Mode is fast convergence, not permanent volatility.
CALIBRATION_GAME_THRESHOLD = 5

# Standard Elo scale: a 400-point Final Rating gap implies a 10x expected
# performance ratio. Reused here since our tier-based scores are already
# calibrated on roughly this scale (400 points per tier).
ELO_SCALE = 400.0


@dataclass
class MatchRatingContext:
    """Everything ExpectedPerformanceUpdateStrategy needs beyond the player
    themself. `opponent_final_rating`/`opponent_contribution` come from a
    same-position opponent when one can be identified, otherwise from the
    opposing team's average - see MatchService._find_opponent_reference."""

    won: bool
    own_contribution: float
    opponent_final_rating: float
    opponent_contribution: float


class RatingUpdateStrategy(ABC):
    @abstractmethod
    def update(self, player: Player, context: MatchRatingContext) -> float:
        """Return the player's new internal_rating after one match."""


class SimpleWinLossUpdateStrategy(RatingUpdateStrategy):
    """Flat +-K adjustment from win/loss alone. Kept as a simple fallback/
    testing strategy - ExpectedPerformanceUpdateStrategy is the default the
    project is meant to converge on (see its docstring)."""

    def __init__(self, normal_k: float = 20.0, calibration_k: float = 75.0) -> None:
        self.normal_k = normal_k
        self.calibration_k = calibration_k

    def update(self, player: Player, context: MatchRatingContext) -> float:
        k = self.calibration_k if player.calibration_mode else self.normal_k
        return player.internal_rating + (k if context.won else -k)


class ExpectedPerformanceUpdateStrategy(RatingUpdateStrategy):
    """Internal Rating moves on *actual vs expected* performance, not on
    win/loss alone: a heavy favorite that performs exactly as expected
    barely moves; a big underdog that dramatically outperforms jumps.

    Expected performance is the standard Elo win-probability curve applied
    to the Final Rating gap against a same-position opponent (or the
    opposing team's average if no clean position match exists). Actual
    performance is each side's Contribution Score expressed as a share of
    the two combined - the same 0..1 shape as the Elo expectation, so the
    two are directly comparable."""

    def __init__(
        self, normal_k: float = 20.0, calibration_k: float = 75.0, elo_scale: float = ELO_SCALE
    ) -> None:
        self.normal_k = normal_k
        self.calibration_k = calibration_k
        self.elo_scale = elo_scale

    def update(self, player: Player, context: MatchRatingContext) -> float:
        expected = 1.0 / (
            1.0 + 10 ** ((context.opponent_final_rating - player.final_rating) / self.elo_scale)
        )

        total_contribution = context.own_contribution + context.opponent_contribution
        actual = context.own_contribution / total_contribution if total_contribution > 0 else 0.5

        k = self.calibration_k if player.calibration_mode else self.normal_k
        return player.internal_rating + k * (actual - expected)
