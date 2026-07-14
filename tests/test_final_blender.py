from __future__ import annotations

import pytest

from app.rating.final_blender import FinalRatingBlender


def test_zero_games_uses_initial_base_weight():
    blender = FinalRatingBlender(initial_base_weight=0.9, plateau_base_weight=0.3, games_to_plateau=20)
    result = blender.blend(base_rating=1000.0, internal_rating=0.0, games_played=0)
    assert result == pytest.approx(900.0)


def test_plateau_games_uses_plateau_base_weight():
    blender = FinalRatingBlender(initial_base_weight=0.9, plateau_base_weight=0.3, games_to_plateau=20)
    result = blender.blend(base_rating=1000.0, internal_rating=0.0, games_played=20)
    assert result == pytest.approx(300.0)


def test_games_beyond_plateau_stay_capped_at_plateau_weight():
    blender = FinalRatingBlender(initial_base_weight=0.9, plateau_base_weight=0.3, games_to_plateau=20)
    result = blender.blend(base_rating=1000.0, internal_rating=0.0, games_played=200)
    assert result == pytest.approx(300.0)


def test_weight_transitions_linearly_between_endpoints():
    blender = FinalRatingBlender(initial_base_weight=0.9, plateau_base_weight=0.3, games_to_plateau=20)
    midpoint = blender.base_weight(games_played=10)
    assert midpoint == pytest.approx(0.6)
