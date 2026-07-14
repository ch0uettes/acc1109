from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class RatingHistory(BaseModel):
    id: Optional[int] = None
    server_id: Optional[int] = None
    player_id: int
    recorded_at: datetime
    official_rating: float
    internal_rating: float
    reason: str

    @property
    def final_rating(self) -> float:
        return self.official_rating + self.internal_rating
