from __future__ import annotations

import pytest

from app.rating.resolver import RatingCaseResolver, TierSnapshot, seed_rating_for_tier
from app.utils.enums import Division, RatingSource, Tier


def test_resolve_current_season_uses_tier_score_and_high_confidence():
    resolver = RatingCaseResolver()
    current = TierSnapshot(Tier.GOLD, Division.II, 40)

    resolution = resolver.resolve_current_season(current, peak=None)

    assert resolution.official_rating == 1200 + 200 + 40
    assert resolution.seed_rating is None
    assert resolution.rating_source == RatingSource.CURRENT_SEASON
    assert resolution.confidence == pytest.approx(0.98)
    assert resolution.calibration_mode is False


def test_resolve_current_season_carries_peak_as_metadata_only():
    resolver = RatingCaseResolver()
    current = TierSnapshot(Tier.PLATINUM, Division.II, 0)
    peak = TierSnapshot(Tier.DIAMOND, Division.IV, 0)

    resolution = resolver.resolve_current_season(current, peak)

    # peak must never influence official_rating - it's metadata only
    assert resolution.official_rating == 1600 + 200
    assert resolution.peak_tier == Tier.DIAMOND


def test_resolve_manual_computes_official_rating_with_manual_confidence():
    resolver = RatingCaseResolver()
    resolution = resolver.resolve_manual(TierSnapshot(Tier.SILVER, Division.I, 10))

    assert resolution.official_rating == 800 + 300 + 10
    assert resolution.seed_rating is None
    assert resolution.rating_source == RatingSource.MANUAL
    assert resolution.confidence == pytest.approx(0.85)
    assert resolution.calibration_mode is False


def test_resolve_seed_never_computes_official_rating():
    resolver = RatingCaseResolver()
    resolution = resolver.resolve_seed(Tier.GOLD)

    assert resolution.official_rating is None
    assert resolution.seed_rating == pytest.approx(seed_rating_for_tier(Tier.GOLD))
    assert resolution.tier == Tier.UNRANKED
    assert resolution.rating_source == RatingSource.SEED
    assert resolution.confidence == pytest.approx(0.25)
    assert resolution.calibration_mode is True


def test_resolve_seed_keeps_peak_as_metadata_only_and_does_not_score_it():
    resolver = RatingCaseResolver()
    peak = TierSnapshot(Tier.DIAMOND, Division.IV, 500)

    resolution = resolver.resolve_seed(Tier.BRONZE, peak)

    assert resolution.peak_tier == Tier.DIAMOND
    # a Diamond peak must NOT leak into the (Bronze-judged) seed_rating
    assert resolution.seed_rating == pytest.approx(seed_rating_for_tier(Tier.BRONZE))


def test_seed_rating_for_tier_lands_mid_tier():
    low = seed_rating_for_tier(Tier.SILVER)
    assert 800 < low < 1200  # strictly inside Silver's 400-point span
