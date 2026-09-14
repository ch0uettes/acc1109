from __future__ import annotations

from typing import Optional

from app.models.player import Player
from app.rating.base import RatingCalculator
from app.utils.enums import Division, Tier

TIER_BASE_SCORE: dict[Tier, float] = {
    Tier.IRON: 0,
    Tier.BRONZE: 400,
    Tier.SILVER: 800,
    Tier.GOLD: 1200,
    Tier.PLATINUM: 1600,
    Tier.EMERALD: 2000,
    Tier.DIAMOND: 2400,
    Tier.MASTER: 2800,
    # UNRANKED never goes through this table in practice (Case 3 uses
    # Estimated Rating instead) - present only so a manually-entered
    # UNRANKED player doesn't crash the manual-entry recompute path.
    Tier.UNRANKED: 0,
}

DIVISION_STEP = 100

DIVISION_OFFSET: dict[Division, float] = {
    Division.IV: 0,
    Division.III: 1 * DIVISION_STEP,
    Division.II: 2 * DIVISION_STEP,
    Division.I: 3 * DIVISION_STEP,
}

MASTER_STAGE_STEP = 300

# Official Rating's current-tier-vs-peak-tier structure: a current tier at
# or near Peak Tier is trusted as-is (an in-form player's current rank IS
# their skill read, full stop). Only once the gap reaches
# PEAK_BLEND_GAP_THRESHOLD does Peak Tier start getting pulled in - the
# player may be rusty/returning rather than genuinely weaker now, so a
# still-recent Peak Tier deserves a real say rather than being ignored
# entirely. The pull-in ramps linearly over PEAK_BLEND_RAMP_WIDTH more
# points of gap (reaching the full PEAK_BLEND_PEAK_WEIGHT only once the gap
# clears threshold+ramp) instead of jumping straight to full weight the
# instant the gap crosses the threshold - a hard jump there would mean one
# more LP of decay at exactly the wrong moment could swing Official Rating
# by tens of points, which is the same cliff-edge problem this project
# otherwise avoids by using smooth Logistic curves everywhere else (see
# app/balance/features/scaling.py's LogisticNormalizer).
PEAK_BLEND_GAP_THRESHOLD = 200.0
PEAK_BLEND_RAMP_WIDTH = 200.0
PEAK_BLEND_CURRENT_WEIGHT = 0.65
PEAK_BLEND_PEAK_WEIGHT = 0.35


def blend_current_and_peak(current_score: float, peak_score: Optional[float]) -> float:
    """current_score alone when there's no Peak Tier reading, when current
    is at/above Peak Tier, or when the gap (peak-tier score minus
    current-tier score - signed, not absolute: a player currently
    *exceeding* their recorded peak should never be dragged down by a
    stale/lower peak entry, only a player sitting below their peak gets the
    blend) hasn't yet reached PEAK_BLEND_GAP_THRESHOLD. Past the threshold,
    Peak Tier's weight ramps linearly from 0 up to PEAK_BLEND_PEAK_WEIGHT
    over the next PEAK_BLEND_RAMP_WIDTH points of gap, so the transition is
    continuous - the score just past the threshold is nearly identical to
    the score just before it, not a sudden jump to a 65/35 split."""
    if peak_score is None:
        return current_score
    gap = peak_score - current_score
    if gap <= PEAK_BLEND_GAP_THRESHOLD:
        return current_score
    peak_weight = PEAK_BLEND_PEAK_WEIGHT * min(1.0, (gap - PEAK_BLEND_GAP_THRESHOLD) / PEAK_BLEND_RAMP_WIDTH)
    return (1.0 - peak_weight) * current_score + peak_weight * peak_score


class OfficialRatingCalculator(RatingCalculator):
    """Riot tier + division + LP based rating. Iron~Diamond each span 400
    points (4 divisions x 100). Master no longer splits into a separate
    Grandmaster/Challenger tier - LP climbs unbounded above the Master
    base score instead, since real GM/Challenger cutoffs are server-relative
    and don't fit a fixed point table."""

    def calculate(self, player: Player) -> float:
        return self.calculate_from(player.tier, player.division, player.lp)

    def calculate_from(self, tier: Tier, division: Division, lp: int) -> float:
        """Pure tier/division/lp -> score, independent of any specific
        Player instance. Needed so Case 2 can score a *peak* season's
        tier/division/lp rather than the player's current (nonexistent) rank."""
        base = TIER_BASE_SCORE[tier]
        if tier == Tier.MASTER:
            return base + lp
        return base + DIVISION_OFFSET[division] + lp


def master_stage_from(tier: Tier, lp: int) -> int | None:
    """Display-only stage number (1, 2, 3, ...) for a Master+ tier, stepping
    up every MASTER_STAGE_STEP LP. None if not Master. Takes raw tier/lp so
    it works for both a player's current tier and their peak tier."""
    if tier != Tier.MASTER:
        return None
    return int(lp // MASTER_STAGE_STEP) + 1


def master_stage(player: Player) -> int | None:
    """Display-only stage number for a player's *current* tier."""
    return master_stage_from(player.tier, player.lp)
