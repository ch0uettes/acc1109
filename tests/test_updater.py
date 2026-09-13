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


def test_expected_performance_no_contribution_data_falls_back_to_result_signal_only():
    """With no contribution data on either side, performance_signal cancels
    to (near) zero (actual defaults to the neutral 0.5, same as expected
    for equal ratings) - the update is then driven entirely by whether the
    match was actually won, not silently zeroed out regardless of result."""
    strategy = ExpectedPerformanceUpdateStrategy(normal_k=20.0)
    player = _make_player(official_rating=1500.0, internal_rating=0.0)
    # player.final_rating blends official_rating down (0.9 base weight at
    # games_played=0); match the opponent to that exact blended value so
    # the Elo expectation comes out to precisely 0.5.
    opponent_rating = player.final_rating

    win_context = _context(
        won=True, own_contribution=0.0, opponent_final_rating=opponent_rating, opponent_contribution=0.0
    )
    loss_context = _context(
        won=False, own_contribution=0.0, opponent_final_rating=opponent_rating, opponent_contribution=0.0
    )

    # performance_signal is 0 either way (0.5 actual - 0.5 expected);
    # result_signal is +0.5 on a win, -0.5 on a loss - with the default
    # 0.5/0.5 weighting that's a +-5.0 swing at k=20.
    assert strategy.update(player, win_context) == pytest.approx(5.0, abs=1e-6)
    assert strategy.update(player, loss_context) == pytest.approx(-5.0, abs=1e-6)


def test_expected_performance_win_beats_loss_at_identical_performance():
    """Core invariant: holding contribution/opponent-rating fixed, winning
    must always net a higher update than losing - this is exactly the bug
    (context.won was previously ignored entirely, see git history)."""
    strategy = ExpectedPerformanceUpdateStrategy(normal_k=20.0)
    player = _make_player(official_rating=1500.0, internal_rating=0.0)

    same_performance = dict(own_contribution=50.0, opponent_final_rating=1500.0, opponent_contribution=50.0)
    update_win = strategy.update(player, _context(won=True, **same_performance))
    update_loss = strategy.update(player, _context(won=False, **same_performance))

    assert update_win > update_loss


def test_expected_performance_a_win_with_bad_performance_can_still_net_a_decrease():
    """A win doesn't unconditionally raise the rating - badly underperforming
    a strong expectation can still net a decrease despite winning."""
    strategy = ExpectedPerformanceUpdateStrategy(normal_k=20.0)
    player = _make_player(official_rating=1500.0, internal_rating=0.0)

    # heavy favorite (expected ~0.9) who barely contributed (actual ~0.1)
    context = _context(won=True, own_contribution=10.0, opponent_final_rating=880.0, opponent_contribution=90.0)
    new_rating = strategy.update(player, context)

    assert new_rating < 0


def test_expected_performance_a_loss_with_great_performance_can_still_net_an_increase():
    """A loss doesn't unconditionally lower the rating - dramatically
    outperforming a weak expectation can still net an increase despite
    losing, so this isn't just win/loss wearing a performance costume."""
    strategy = ExpectedPerformanceUpdateStrategy(normal_k=20.0)
    player = _make_player(official_rating=1500.0, internal_rating=0.0)

    # heavy underdog (expected ~0.1) who dominated the box score (actual ~0.9)
    context = _context(won=False, own_contribution=90.0, opponent_final_rating=2120.0, opponent_contribution=10.0)
    new_rating = strategy.update(player, context)

    assert new_rating > 0


def test_expected_performance_calibration_mode_amplifies_swing():
    strategy = ExpectedPerformanceUpdateStrategy(normal_k=20.0, calibration_k=75.0)
    calibration_player = _make_player(official_rating=1500.0, internal_rating=0.0, calibration_mode=True)
    normal_player = _make_player(official_rating=1500.0, internal_rating=0.0, calibration_mode=False)

    context = _context(won=True, own_contribution=80.0, opponent_final_rating=1500.0, opponent_contribution=20.0)
    calibration_delta = strategy.update(calibration_player, context)
    normal_delta = strategy.update(normal_player, context)

    assert calibration_delta > normal_delta > 0
