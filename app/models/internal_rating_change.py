from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class InternalRatingChange(BaseModel):
    """Audit row for every admin override of Internal Rating (see
    PlayerService.override_internal_rating). Unlike Seed Rating,
    internal_rating is normally earned automatically through match
    results (rating.updater.ExpectedPerformanceUpdateStrategy) - this
    table only covers the manual-override path, not every match-driven
    update, mirroring SeedRatingChange's shape exactly."""

    id: Optional[int] = None
    player_id: int
    server_id: int
    old_internal_rating: float
    new_internal_rating: float
    changed_by: str
    changed_at: datetime
    reason: Optional[str] = None
