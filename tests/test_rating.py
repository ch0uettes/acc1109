from __future__ import annotations

from app.models.player import Player
from app.rating.combiner import FinalRatingCalculator
from app.rating.internal import InternalRatingCalculator
from app.rating.official import OfficialRatingCalculator, master_stage
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
