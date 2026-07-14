from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

from app.utils.enums import Position


class RolePreference(BaseModel):
    """A resolved Main/Sub pair for one player in one match - the output
    of RolePreferenceManager, and the input PositionAssigner searches
    against. `sub` may be None (no fallback role declared/known)."""

    main: Position
    sub: Optional[Position] = None


class RoleRecommendation(BaseModel):
    """PositionAnalyzer's output: what Riot match history suggests, with
    confidence ratios so a caller can judge how trustworthy it is. Never
    written back into a player automatically after the first registration -
    it's reference-only from then on (see Player.recommended_main_role)."""

    main: Position
    main_ratio: float
    sub: Optional[Position] = None
    sub_ratio: Optional[float] = None
    sample_size: int
