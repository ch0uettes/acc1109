from __future__ import annotations

import pytest

from app.rating.final_blender import FinalRatingBlender


def _blender() -> FinalRatingBlender:
    return FinalRatingBlender(initial_base_weight=0.9, plateau_base_weight=0.3, games_to_plateau=20)


@pytest.mark.parametrize("games", [0, 4, 20, 200])
def test_no_correction_keeps_the_tier_score_however_many_games(games):
    # Regression: internal_rating (0 here) used to be averaged in, dragging
    # a 20-game regular down to 30% of their tier score.
    assert _blender().blend(base_rating=1000.0, internal_rating=0.0, games_played=games) == pytest.approx(1000.0)


def test_a_new_player_gets_10_percent_of_the_correction():
    assert _blender().blend(base_rating=1000.0, internal_rating=100.0, games_played=0) == pytest.approx(1010.0)


def test_at_the_plateau_70_percent_of_the_correction_counts():
    assert _blender().blend(base_rating=1000.0, internal_rating=100.0, games_played=20) == pytest.approx(1070.0)
    assert _blender().blend(base_rating=1000.0, internal_rating=-100.0, games_played=200) == pytest.approx(930.0)


def test_a_regular_is_never_rated_below_a_newcomer_of_a_lower_tier_without_cause():
    regular = _blender().blend(base_rating=1830.0, internal_rating=0.0, games_played=20)
    newcomer = _blender().blend(base_rating=1430.0, internal_rating=0.0, games_played=0)
    assert regular > newcomer


def test_weight_transitions_linearly_between_endpoints():
    assert _blender().base_weight(games_played=10) == pytest.approx(0.6)
