from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.rating.official import DIVISION_OFFSET, OfficialRatingCalculator, TIER_BASE_SCORE
from app.rating.official_strategy import CurrentTierPriorityStrategy, OfficialRatingStrategy
from app.utils.enums import Division, RatingSource, Tier

# Confidence bands: a Riot-confirmed current-season rank is near-certain,
# an operator-entered exact tier is trusted but not machine-verified, and a
# rough operator judgment (Seed Rating, no real data at all) starts out
# almost meaningless until Calibration Mode corrects it via actual games.
CONFIDENCE_CURRENT_SEASON = 0.98
CONFIDENCE_MANUAL = 0.85
CONFIDENCE_SEED = 0.25

# A Seed Rating always assumes this LP within whatever division is given,
# since there's no real LP for a player with no current-season data. With
# the default division (III) this reproduces the old flat "roughly mid-tier"
# guess (100 + 50 = 150), but an operator who has an actual division-level
# read (e.g. a known peak rank) can now pass it in for real precision.
ASSUMED_SEED_LP = 50


@dataclass
class TierSnapshot:
    """A tier/division/lp triple - used for the current-season and (purely
    informational) peak-tier inputs to the resolver."""

    tier: Tier
    division: Division
    lp: int


@dataclass
class RatingResolution:
    """Everything needed to construct a Player's rating fields. Official
    Rating and Seed Rating are mutually exclusive - exactly one of them is
    set, matching Player.base_rating's own either/or logic."""

    tier: Tier
    division: Division
    lp: int
    peak_tier: Optional[Tier]
    peak_division: Optional[Division]
    peak_lp: Optional[int]
    official_rating: Optional[float]
    seed_rating: Optional[float]
    confidence: float
    rating_source: RatingSource
    calibration_mode: bool


def seed_rating_for_tier(tier: Tier, division: Division = Division.III) -> float:
    """Converts an operator's tier (+ optional division) judgment into a
    score, on the same scale as OfficialRatingCalculator so the two are
    comparable. Division defaults to III (roughly mid-tier) when the
    operator only has a coarse read; pass a real division for precision."""
    return TIER_BASE_SCORE[tier] + DIVISION_OFFSET[division] + ASSUMED_SEED_LP


class RatingCaseResolver:
    """Case 1: Riot confirms a current-season tier -> Official Rating,
    high confidence, no calibration needed.
    Case 2/3 (no current-season tier, Peak Tier present or not - Peak Tier
    is never a scoring input either way): an operator must supply a Seed
    Rating tier judgment -> low confidence, Calibration Mode on so a
    handful of real games can correct a bad initial guess quickly."""

    def __init__(self, strategy: Optional[OfficialRatingStrategy] = None) -> None:
        self.strategy = strategy or CurrentTierPriorityStrategy()

    def resolve_current_season(self, current: TierSnapshot, peak: Optional[TierSnapshot]) -> RatingResolution:
        official_rating = OfficialRatingCalculator().calculate_from(current.tier, current.division, current.lp)
        return RatingResolution(
            tier=current.tier,
            division=current.division,
            lp=current.lp,
            peak_tier=peak.tier if peak else None,
            peak_division=peak.division if peak else None,
            peak_lp=peak.lp if peak else None,
            official_rating=official_rating,
            seed_rating=None,
            confidence=CONFIDENCE_CURRENT_SEASON,
            rating_source=RatingSource.CURRENT_SEASON,
            calibration_mode=False,
        )

    def resolve_manual(self, current: TierSnapshot) -> RatingResolution:
        """An operator directly entering an exact tier/division/lp they
        know to be true (e.g. a friend without a linked Riot ID)."""
        official_rating = OfficialRatingCalculator().calculate_from(current.tier, current.division, current.lp)
        return RatingResolution(
            tier=current.tier,
            division=current.division,
            lp=current.lp,
            peak_tier=None,
            peak_division=None,
            peak_lp=None,
            official_rating=official_rating,
            seed_rating=None,
            confidence=CONFIDENCE_MANUAL,
            rating_source=RatingSource.MANUAL,
            calibration_mode=False,
        )

    def resolve_seed(
        self, seed_tier: Tier, peak: Optional[TierSnapshot] = None, seed_division: Division = Division.III
    ) -> RatingResolution:
        return RatingResolution(
            tier=Tier.UNRANKED,
            division=Division.IV,
            lp=0,
            peak_tier=peak.tier if peak else None,
            peak_division=peak.division if peak else None,
            peak_lp=peak.lp if peak else None,
            official_rating=None,
            seed_rating=seed_rating_for_tier(seed_tier, seed_division),
            confidence=CONFIDENCE_SEED,
            rating_source=RatingSource.SEED,
            calibration_mode=True,
        )
