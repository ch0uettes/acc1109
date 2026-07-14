from __future__ import annotations

import pytest

from app.balance.features.scaling import (
    LinearNormalizer,
    LogarithmicNormalizer,
    LogisticNormalizer,
    PiecewiseNormalizer,
)


def test_linear_normalizer_scales_and_clips():
    normalizer = LinearNormalizer(max_value=100.0)
    assert normalizer(0.0) == 0.0
    assert normalizer(50.0) == pytest.approx(0.5)
    assert normalizer(200.0) == 1.0  # clipped, never exceeds 1.0


def test_linear_normalizer_zero_max_never_divides_by_zero():
    normalizer = LinearNormalizer(max_value=0.0)
    assert normalizer(10.0) == 0.0


def test_logistic_normalizer_is_smooth_across_the_midpoint():
    # The whole point: no single raw value flips the score - values just
    # below and just above the midpoint score nearly identically, unlike
    # a hard threshold cutoff.
    normalizer = LogisticNormalizer(midpoint=400.0, steepness=0.0075)
    just_below = normalizer(399.0)
    just_above = normalizer(401.0)
    assert just_below == pytest.approx(just_above, abs=0.01)
    assert normalizer(400.0) == pytest.approx(0.5, abs=1e-6)
    assert normalizer(0.0) < normalizer(400.0) < normalizer(2000.0)


def test_logarithmic_normalizer_compresses_large_values():
    normalizer = LogarithmicNormalizer(scale=200_000.0)
    assert normalizer(0.0) == 0.0
    small, large = normalizer(5_000.0), normalizer(50_000.0)
    assert small < large
    # A 10x jump in raw value is nowhere near a 10x jump in score.
    assert large < small * 10


def test_logarithmic_normalizer_clips_past_scale():
    normalizer = LogarithmicNormalizer(scale=1_000.0)
    assert normalizer(1_000_000.0) == 1.0


def test_piecewise_normalizer_interpolates_between_breakpoints():
    normalizer = PiecewiseNormalizer([(0.0, 0.0), (2.0, 0.2), (10.0, 1.0)])
    assert normalizer(0.0) == 0.0
    assert normalizer(1.0) == pytest.approx(0.1)
    assert normalizer(2.0) == pytest.approx(0.2)
    assert normalizer(6.0) == pytest.approx(0.6)


def test_piecewise_normalizer_clamps_outside_breakpoint_range():
    normalizer = PiecewiseNormalizer([(0.0, 0.0), (10.0, 1.0)])
    assert normalizer(-5.0) == 0.0
    assert normalizer(100.0) == 1.0
