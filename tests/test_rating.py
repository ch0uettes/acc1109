from __future__ import annotations

import pytest

from app.models.player import Player
from app.rating.combiner import FinalRatingCalculator
from app.rating.internal import InternalRatingCalculator
from app.rating.official import OfficialRatingCalculator, blend_current_and_peak, master_stage
from app.rating.official_strategy import CurrentTierPriorityStrategy
from app.utils.enums import Division, Position, Tier


def _make_player(**overrides) -> Player:
    defaults = dict(nickname="tester", tier=Tier.GOLD, division=Division.I, lp=50, main_role=Position.MID)
    defaults.update(overrides)
    return Player(**defaults)


def test_official_rating_uses_tier_division_and_lp():
    player = _make_player(tier=Tier.GOLD, division=Division.I, lp=50)
    assert OfficialRatingCalculator().calculate(player) == 1200 + 300 + 50


def test_division_step_is_100_points():
    calc = OfficialRatingCalculator()
    lowest = _make_player(tier=Tier.SILVER, division=Division.IV, lp=0)
    highest = _make_player(tier=Tier.SILVER, division=Division.I, lp=0)
    assert calc.calculate(highest) - calc.calculate(lowest) == 300


def test_master_tier_ignores_division_and_uses_lp_directly():
    player = _make_player(tier=Tier.MASTER, division=Division.IV, lp=650)
    assert OfficialRatingCalculator().calculate(player) == 2800 + 650


def test_master_stage_steps_every_300_lp():
    assert master_stage(_make_player(tier=Tier.MASTER, lp=0)) == 1
    assert master_stage(_make_player(tier=Tier.MASTER, lp=299)) == 1
    assert master_stage(_make_player(tier=Tier.MASTER, lp=300)) == 2
    assert master_stage(_make_player(tier=Tier.MASTER, lp=650)) == 3
    assert master_stage(_make_player(tier=Tier.GOLD, lp=50)) is None


def test_final_rating_is_plain_sum_by_default():
    player = _make_player(tier=Tier.GOLD, division=Division.I, lp=50, internal_rating=30)
    calc = FinalRatingCalculator(OfficialRatingCalculator(), InternalRatingCalculator())
    assert calc.calculate(player) == (1200 + 300 + 50) + 30


# --- blend_current_and_peak: Official Rating's current-tier/peak-tier structure ---


def test_blend_uses_current_alone_when_no_peak_reading():
    assert blend_current_and_peak(1800, None) == 1800


def test_blend_uses_current_alone_when_gap_under_threshold():
    assert blend_current_and_peak(1800, 1800 + 199) == 1800


def test_blend_uses_current_alone_when_current_is_at_or_above_peak():
    assert blend_current_and_peak(2400, 1800) == 2400  # current exceeds a stale/lower peak
    assert blend_current_and_peak(1800, 1800) == 1800  # exactly at peak


def test_blend_weights_current_and_peak_once_gap_reaches_threshold():
    assert blend_current_and_peak(1800, 2000) == pytest.approx(0.65 * 1800 + 0.35 * 2000)  # gap == 200 exactly
    assert blend_current_and_peak(1800, 2400) == pytest.approx(0.65 * 1800 + 0.35 * 2400)  # gap == 600


def test_current_tier_priority_strategy_matches_blend_current_and_peak():
    # near peak (gap < 200) -> current alone
    near_peak = _make_player(
        tier=Tier.PLATINUM, division=Division.II, lp=50,  # 1600+200+50=1850
        peak_tier=Tier.PLATINUM, peak_division=Division.I, peak_lp=0,  # 1600+300+0=1900, gap=50
    )
    assert CurrentTierPriorityStrategy().calculate(near_peak) == 1850

    # far below peak (gap >= 200) -> blended
    far_below_peak = _make_player(
        tier=Tier.PLATINUM, division=Division.II, lp=0,  # 1600+200+0=1800
        peak_tier=Tier.DIAMOND, peak_division=Division.IV, peak_lp=0,  # 2400, gap=600
    )
    assert CurrentTierPriorityStrategy().calculate(far_below_peak) == pytest.approx(0.65 * 1800 + 0.35 * 2400)


def test_current_tier_priority_strategy_ignores_incomplete_peak_data():
    # peak_tier set but peak_division/peak_lp missing - too incomplete to
    # score, must not raise and must fall back to current alone.
    player = _make_player(tier=Tier.GOLD, division=Division.I, lp=50, peak_tier=Tier.DIAMOND)
    assert CurrentTierPriorityStrategy().calculate(player) == 1200 + 300 + 50


def test_current_tier_priority_strategy_returns_none_for_unranked():
    player = _make_player(tier=Tier.UNRANKED)
    assert CurrentTierPriorityStrategy().calculate(player) is None
