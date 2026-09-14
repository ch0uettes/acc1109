from __future__ import annotations

import statistics

from app.balance.config import DEFAULT_NORMALIZATION_CONFIG, NormalizationConfig
from app.balance.features.base import FeaturePriority, IBalanceFeature
from app.balance.features.scaling import LogisticNormalizer
from app.models.team import Team


class OutlierPenaltyFeature(IBalanceFeature):
    """Responsibility: does any ONE team sit way off from the rest -
    "극단적인 팀 생성 방지". Deliberately isolated from MeanBalanceFeature
    (which looks at every team's average collectively, as a distribution)
    - this Feature only cares about the single worst-off team, so a
    roster where every team's average is already close together scores
    near-zero here even if MeanBalanceFeature also happens to be near-zero,
    but a roster with one wildly-off team scores badly here specifically,
    regardless of how tightly the *other* teams cluster.

    Computed as the maximum absolute deviation of any one team's average
    from the global mean - this isolates the single worst offender
    (unlike variance/stddev, which are influenced by every team's spread
    collectively and can't tell "one bad team" apart from "everyone
    moderately spread out"). Normalized via a Logistic curve calibrated
    to ramp up sharply, per the PRD's "Outlier가 있으면 Penalty가 급격히
    증가해야 한다"."""

    name = "outlier_penalty"
    category = "rating"
    description = "가장 크게 벗어난 팀 하나의 절대 편차 (Max Absolute Deviation)"
    default_enabled = True
    default_weight = 0.27
    priority = FeaturePriority.CRITICAL

    def __init__(self, config: NormalizationConfig = DEFAULT_NORMALIZATION_CONFIG) -> None:
        self._normalizer = LogisticNormalizer(
            config.outlier_penalty_midpoint, config.outlier_penalty_steepness
        )

    def evaluate_raw(self, teams: list[Team]) -> float:
        if len(teams) < 3:
            # With exactly 2 teams there's only one degree of freedom (the
            # gap between the two averages), so "the single worst team's
            # deviation from the mean" is mathematically identical to (a
            # fixed multiple of) MeanBalanceFeature's stdev-of-means - no
            # amount of reformulating the reference point changes that for
            # a pair of numbers. Scoring it anyway would silently double
            # the effective weight of "team average gap" under two
            # different feature names. It only starts measuring something
            # MeanBalanceFeature can't see once there are 3+ teams (e.g. a
            # multi-lobby event) to tell "one bad team" apart from
            # "everyone moderately spread out." Returning a constant here
            # doesn't affect ranking within a single search (every
            # candidate in a 2-team search gets the same constant), only
            # zeroes out the otherwise-redundant weight.
            return 0.0
        means = [team.average_rating for team in teams]
        global_mean = statistics.fmean(means)
        return max(abs(mean - global_mean) for mean in means)

    def normalize(self, raw: float) -> float:
        return self._normalizer(raw)
