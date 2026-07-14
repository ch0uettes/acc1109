from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.models.contribution import ContributionScore
from app.utils.enums import Position


class MatchPlayerResult(BaseModel):
    player_id: int
    team_index: int
    position: Position
    contribution: ContributionScore


class Match(BaseModel):
    id: Optional[int] = None
    server_id: Optional[int] = None
    played_at: datetime
    participants: list[MatchPlayerResult]
    winning_team_index: int
    ai_mvp_player_id: Optional[int] = None
    user_mvp_player_id: Optional[int] = None
    note: Optional[str] = None
