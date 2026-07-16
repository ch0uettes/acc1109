from __future__ import annotations

from pydantic import BaseModel

from app.utils.enums import Division, Tier


class SeasonTierEntry(BaseModel):
    """One row of OP.GG's season-by-season rank history table for a
    summoner - `season` is OP.GG's own label (e.g. "S2024 S2", "S2025"),
    kept as-is rather than parsed into a structured year/split, since
    nothing here needs to compute with it, only display/store it.
    `tier`/`division`/`lp` are already normalized onto this app's own
    (Tier, Division, lp) scale (Master/Grandmaster/Challenger folded into
    Tier.MASTER with a re-based lp - see app.riot.client._convert_riot_rank,
    reused here so a Grandmaster season and a Grandmaster current rank
    compare correctly on the same scale)."""

    season: str
    tier: Tier
    division: Division
    lp: int
