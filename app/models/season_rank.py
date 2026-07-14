from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.utils.enums import Division, Tier


class PlayerSeasonRank(BaseModel):
    """One point-in-time snapshot of a player's current/peak tier. A new
    row is appended on every registration or profile update rather than
    overwriting - the growing history is what lets skill be inferred across
    season changes (growth trend, dormant periods, when peak was hit)."""

    id: Optional[int] = None
    server_id: Optional[int] = None
    player_id: int
    season: str
    current_tier: Tier
    current_division: Division
    current_lp: int
    peak_tier: Optional[Tier] = None
    peak_division: Optional[Division] = None
    peak_lp: Optional[int] = None
    recorded_at: datetime
