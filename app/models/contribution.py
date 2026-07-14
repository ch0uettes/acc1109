from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class ContributionScore(BaseModel):
    """Breakdown behind a player's MVP candidacy for one match.
    Everything beyond `combat` is a placeholder until real match stats
    (Riot API / OCR) are available."""

    player_id: Optional[int] = None
    combat: float = 0.0
    vision: float = 0.0
    objective: float = 0.0
    economy: float = 0.0
    death_penalty: float = 0.0

    @property
    def total(self) -> float:
        return self.combat + self.vision + self.objective + self.economy - self.death_penalty
