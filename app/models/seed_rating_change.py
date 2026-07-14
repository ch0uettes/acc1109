from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class SeedRatingChange(BaseModel):
    """Audit row for every Seed Rating assignment/change. Seed Rating is
    never player-editable and never auto-computed, so every value that
    ever lands in Player.seed_rating must trace back to one of these -
    including the very first assignment (old_seed_rating=None)."""

    id: Optional[int] = None
    player_id: int
    server_id: int
    old_seed_rating: Optional[float]
    new_seed_rating: float
    changed_by: str
    changed_at: datetime
    reason: Optional[str] = None
