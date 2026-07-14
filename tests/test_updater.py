from __future__ import annotations

import pytest

from app.models.player import Player
from app.rating.updater import (
    ExpectedPerformanceUpdateStrategy,
    MatchRatingContext,
    SimpleWinLossUpdateStrategy,
)
from app.utils.enums import Division, Position, Tier


def _make_player(**overrides) -> Player:
    defaults = dict(
        nickname="tester",
        tier=Tier.GOLD,
        division=Division.I,
        lp=50,
        official_rating=1500.0,
        main_role=Position.MID,
    )
    defaults.update(overrides)
    return Player(**defaults)


def _context(**overrides) -> MatchRatingContext:
    defaults = dict(
        won=True, own_contribution=10.0, opponent_final_rating=1500.0, opponent_contribution=10.0
    )
    defaults.update(overrides)
    return MatchRatingContext(**defaults)


def test_simple_win_loss_normal_player_uses_small_k():
    strategy = SimpleWinLossUpdateStrategy(normal_k=20.0, calibration_k=75.0)
    player = _make_player(internal_rating=0.0, calibration_mode=False)

    assert strategy.update(player, _context(won=True)) == 20.0
    assert strategy.update(player, _context(won=False)) == -20.0


def test_simple_win_loss_calibration_player_uses_large_k():
    strategy = SimpleWinLossUpdateStrategy(normal_k=20.0, calibration_k=75.0)
    player = _make_player(internal_rating=0.0, calibration_mode=True)

    assert strategy.update(player, _context(won=True)) == 75.0
    assert strategy.update(player, _context(won=False)) == -75.0


def test_expected_performance_barely_moves_when_favorite_performs_as_expected():
    """Diamond crushing Gold in contribution is the *expected* outcome -
    actual ~= expected, so the rating should barely move."""
    strategy = ExpectedPerformanceUpdateStrategy(normal_k=20.0)
    diamond = _make_player(official_rating=2400.0, internal_rating=0.0, games_played=0)

    # own_contribution vastly bigger than opponent's -> actual close to 1,
    # matching an expected close to 1 for such a large rating gap
    context = _context(won=True, own_contribution=90.0, opponent_final_rating=1200.0, opponent_contribution=10.0)
    new_rating = strategy.update(diamond, context)

    assert abs(new_rating) < 3.0  # small change either direction


def test_expected_performance_jumps_when_underdog_massively_outperforms():
    """Gold-rated player massively outperforming a Diamond opponent should
    swing Internal Rating up a lot, per the PRD's own example."""
    strategy = ExpectedPerformanceUpdateStrategy(normal_k=20.0)
    gold = _make_player(official_rating=1200.0, internal_rating=0.0, games_played=0)

    context = _context(won=True, own_contribution=90.0, opponent_final_rating=2400.0, opponent_contribution=10.0)
    new_rating = strategy.update(gold, context)

    assert new_rating > 10.0


def test_expected_performance_neutral_falls_back_when_no_contribution_data():
    strategy = ExpectedPerformanceUpdateStrategy(normal_k=20.0)
    player = _make_player(official_rating=1500.0, internal_rating=0.0)
    # player.final_rating blends official_rating down (0.9 base weight at
    # games_played=0); match the opponent to that exact blended value so
    # the Elo expectation comes out to precisely 0.5, isolating the
    # no-contribution-data fallback this test is actually about.
    opponent_rating = player.final_rating

    context = _context(own_contribution=0.0, opponent_final_rating=opponent_rating, opponent_contribution=0.0)
    new_rating = strategy.update(player, context)

    # expected 0.5 (equal ratings) and actual defaults to 0.5 (no
    # contribution data) -> they cancel out to (near) zero change
    assert new_rating == pytest.approx(0.0, abs=1e-6)


def test_expected_performance_calibration_mode_amplifies_swing():
    strategy = ExpectedPerformanceUpdateStrategy(normal_k=20.0, calibration_k=75.0)
    calibration_player = _make_player(official_rating=1500.0, internal_rating=0.0, calibration_mode=True)
    normal_player = _make_player(official_rating=1500.0, internal_rating=0.0, calibration_mode=False)

    context = _context(won=True, own_contribution=80.0, opponent_final_rating=1500.0, opponent_contribution=20.0)
    calibration_delta = strategy.update(calibration_player, context)
    normal_delta = strategy.update(normal_player, context)

    assert calibration_delta > normal_delta > 0
