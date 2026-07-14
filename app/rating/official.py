from __future__ import annotations

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

# When a player has no current-season tier and Peak Tier substitutes for it,
# the peak rating is discounted since the player may not have touched the
# game in a while. See OfficialRatingStrategy.peak_only_decay.
PAST_SEASON_DECAY_FACTOR = 0.95


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
