from __future__ import annotations

import math


class LinearNormalizer:
    """raw / max_value, clipped to [0, 1]. Fits Features whose raw value
    is already in a fixed, interpretable unit with a sensible "this much
    is as bad as it gets" ceiling (e.g. summed role penalties, a
    threshold-style per-lane rating gap)."""

    def __init__(self, max_value: float) -> None:
        self.max_value = max_value

    def __call__(self, raw: float) -> float:
        if self.max_value <= 0:
            return 0.0
        return max(0.0, min(raw / self.max_value, 1.0))


class LogisticNormalizer:
    """Sigmoid centered at `midpoint`, controlled by `steepness`. Ramps
    smoothly from 0 to 1 with no single cutoff - a raw value just below
    vs just above `midpoint` gets nearly the same score. This is the
    direct fix for the cliff-edge problem a Hard Constraint threshold
    creates (e.g. average rating gap 799 passes, 801 is rejected):
    a smooth Soft Penalty never flips a candidate's fate on a single
    point of raw value."""

    def __init__(self, midpoint: float, steepness: float) -> None:
        self.midpoint = midpoint
        self.steepness = steepness

    def __call__(self, raw: float) -> float:
        return 1.0 / (1.0 + math.exp(-self.steepness * (raw - self.midpoint)))


class LogarithmicNormalizer:
    """log(1 + raw) / log(1 + scale), clipped to [0, 1]. Fits Features
    whose raw metric has a huge dynamic range (e.g. team_variance, a
    squared-rating-point unit that can run into the hundreds of
    thousands) - compresses large raw values instead of letting them
    swamp every other Feature's contribution once weighted."""

    def __init__(self, scale: float) -> None:
        self.scale = scale

    def __call__(self, raw: float) -> float:
        if raw <= 0:
            return 0.0
        return max(0.0, min(math.log1p(raw) / math.log1p(self.scale), 1.0))


class PiecewiseNormalizer:
    """Linear interpolation between explicit (raw, score) breakpoints -
    fits Features where "how bad is this gap" isn't a smooth formula but
    a hand-tuned curve (e.g. tier_distribution: a gap of 1 barely
    matters, a gap of 3+ matters a lot more than 3x as much)."""

    def __init__(self, breakpoints: list[tuple[float, float]]) -> None:
        self.breakpoints = sorted(breakpoints, key=lambda point: point[0])

    def __call__(self, raw: float) -> float:
        points = self.breakpoints
        if raw <= points[0][0]:
            return points[0][1]
        if raw >= points[-1][0]:
            return points[-1][1]
        for (x0, y0), (x1, y1) in zip(points, points[1:]):
            if x0 <= raw <= x1:
                if x1 == x0:
                    return y0
                t = (raw - x0) / (x1 - x0)
                return y0 + t * (y1 - y0)
        return points[-1][1]
