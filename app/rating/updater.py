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
    """Internal Rating moves on *actual vs expected*, evaluated on two
    independent axes - not on win/loss alone, and (bug fixed here) not on
    contribution alone either:

    - result_signal: did this side actually win, versus the Elo
      win-probability the rating gap implied?
    - performance_signal: did this side's Contribution Score (share of the
      two sides' combined total) beat that same Elo expectation?

    Both reuse the identical Elo expectation (`expected`, from the Final
    Rating gap against a same-position opponent or the opposing team's
    average), so they're directly comparable 0..1-shaped quantities and
    blending them via `result_weight`/`performance_weight` (they sum to 1)
    doesn't change the existing K-factor scale. A heavy favorite winning
    exactly as expected barely moves either signal; a big underdog that
    wins AND dramatically outperforms jumps on both. Contribution alone
    used to decide the whole update, which meant a losing side with a
    better stat line could still gain rating - result_signal is what
    prevents that: holding performance fixed, a win always nets a higher
    update than a loss.

    `result_weight` defaults to an even 0.5/0.5 split with performance -
    a reasonable starting point, not a finalized product ratio; callers
    that want a different balance pass it in without touching this class."""

    def __init__(
        self,
        normal_k: float = 20.0,
        calibration_k: float = 75.0,
        elo_scale: float = ELO_SCALE,
        result_weight: float = 0.5,
    ) -> None:
        self.normal_k = normal_k
        self.calibration_k = calibration_k
        self.elo_scale = elo_scale
        self.result_weight = result_weight
        self.performance_weight = 1.0 - result_weight

    def update(self, player: Player, context: MatchRatingContext) -> float:
        expected = 1.0 / (
            1.0 + 10 ** ((context.opponent_final_rating - player.final_rating) / self.elo_scale)
        )

        total_contribution = context.own_contribution + context.opponent_contribution
        actual_performance = context.own_contribution / total_contribution if total_contribution > 0 else 0.5
        actual_result = 1.0 if context.won else 0.0

        performance_signal = actual_performance - expected
        result_signal = actual_result - expected
        combined_signal = self.result_weight * result_signal + self.performance_weight * performance_signal

        k = self.calibration_k if player.calibration_mode else self.normal_k
        return player.internal_rating + k * combined_signal
