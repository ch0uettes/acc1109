from __future__ import annotations

from app.ai.contribution import (
    NEUTRAL_FALLBACK_TOTAL,
    DummyContributionScoreCalculator,
    OCRContributionScoreCalculator,
)
from app.ai.mvp import AIMVPSelector
from app.models.match import MatchPlayerResult
from app.models.player import Player
from app.utils.enums import Division, Position, Tier


def _player(rating: float) -> Player:
    # tier/division/lp only need to be valid enough to produce some
    # official_rating; internal_rating stays 0 so final_rating == official.
    return Player(
        nickname="p",
        tier=Tier.DIAMOND,
        division=Division.I,
        lp=0,
        main_role=Position.MID,
        official_rating=rating,
    )


def test_dummy_fallback_does_not_scale_with_player_rating():
    """A missed OCR row shouldn't quietly reward a high-rated player with a
    bigger fallback score than a low-rated one - we have no idea how either
    of them actually played this game."""
    low = DummyContributionScoreCalculator().calculate(_player(500.0), {})
    high = DummyContributionScoreCalculator().calculate(_player(2800.0), {})
    assert low.total == high.total == NEUTRAL_FALLBACK_TOTAL


def test_dummy_fallback_is_on_the_same_scale_as_a_real_ocr_score():
    """Regression test: the fallback used to be player.final_rating / 100,
    which tops out around 20-30 for realistic ratings - roughly 5-10x
    smaller than a typical OCR-derived total. That meant a player whose OCR
    row simply failed to match could never be picked as MVP, no matter how
    well they actually played, purely because of the scale mismatch."""
    average_game_stats = {
        "kills": 4, "deaths": 4, "assists": 6, "cs": 120, "gold": 8000, "damage": 10000, "vision_score": 15,
    }
    real_score = OCRContributionScoreCalculator().calculate(_player(1500.0), average_game_stats)
    fallback_score = DummyContributionScoreCalculator().calculate(_player(1500.0), {})

    assert fallback_score.total == real_score.total  # both represent "an average game"


def test_ocr_calculator_uses_the_scaled_fallback_when_a_players_row_is_missing():
    fallback_used = OCRContributionScoreCalculator().calculate(_player(1500.0), {})
    assert fallback_used.total == NEUTRAL_FALLBACK_TOTAL


def test_a_player_with_a_missed_ocr_row_is_not_automatically_excluded_from_mvp():
    """End-to-end: 9 players have ordinary OCR stats, 1 player's row failed
    to match and falls back to the neutral placeholder. Under the old
    rating-derived fallback (final_rating/100 ~= 15-25) that player could
    never beat a real score no matter how the other 9 actually played; the
    same-scale neutral placeholder means an ordinary/weak real game doesn't
    automatically outrank a missed-row teammate."""
    calc = OCRContributionScoreCalculator()
    ordinary_stats = {"kills": 3, "deaths": 5, "assists": 4, "cs": 100, "gold": 7000, "damage": 8000, "vision_score": 10}
    assert NEUTRAL_FALLBACK_TOTAL > calc.calculate(_player(1500.0), ordinary_stats).total

    participants = [
        MatchPlayerResult(
            player_id=i, team_index=0 if i < 5 else 1, position=Position.MID,
            contribution=calc.calculate(_player(1500.0), ordinary_stats if i != 3 else {}),
        )
        for i in range(10)
    ]

    assert AIMVPSelector().select(participants) == 3
