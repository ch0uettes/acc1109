from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, computed_field

from app.models.contribution import ContributionScore
from app.utils.enums import Position


class MatchPlayerResult(BaseModel):
    player_id: int
    team_index: int
    position: Position
    contribution: ContributionScore
    # This match's effect on the player, kept so deleting the match can undo
    # exactly its share. None on matches recorded before they were kept.
    internal_rating_before: Optional[float] = None
    internal_rating_after: Optional[float] = None
    exited_calibration: Optional[bool] = None


class Match(BaseModel):
    id: Optional[int] = None
    server_id: Optional[int] = None
    played_at: datetime
    participants: list[MatchPlayerResult]
    winning_team_index: int
    ai_mvp_player_id: Optional[int] = None
    user_mvp_player_id: Optional[int] = None
    note: Optional[str] = None
    team_run_at: Optional[datetime] = None

    @computed_field
    @property
    def revertible(self) -> bool:
        return bool(self.participants) and all(
            p.internal_rating_before is not None and p.internal_rating_after is not None
            for p in self.participants
        )
