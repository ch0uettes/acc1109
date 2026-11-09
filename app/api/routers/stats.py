from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_actor, get_db
from app.models.decision_log import DecisionLogEntry
from app.models.match import Match
from app.models.player import Player
from app.services.stats_service import StatsService
from app.services.team_service import TeamService

router = APIRouter(prefix="/servers/{server_id}/stats", tags=["stats"], dependencies=[Depends(get_actor)])


@router.get("/leaderboard", response_model=list[Player])
def leaderboard(server_id: int, db: Session = Depends(get_db)) -> list[Player]:
    return StatsService(db, server_id).leaderboard()


@router.get("/players/{player_id}/matches", response_model=list[Match])
def player_match_history(server_id: int, player_id: int, db: Session = Depends(get_db)) -> list[Match]:
    return StatsService(db, server_id).player_match_history(player_id)


@router.get("/ai-mvp-accuracy", response_model=float)
def ai_mvp_accuracy(server_id: int, db: Session = Depends(get_db)) -> float:
    return StatsService(db, server_id).ai_mvp_accuracy()


@router.get("/decisions", response_model=list[DecisionLogEntry])
def recent_decisions(server_id: int, limit: int = 20, db: Session = Depends(get_db)) -> list[DecisionLogEntry]:
    return TeamService(db, server_id).recent_decisions(limit=limit)


class PlayerRecord(BaseModel):
    player_id: int
    nickname: str
    is_active: bool
    final_rating: float
    games: int
    wins: int
    losses: int
    ai_mvp: int
    user_mvp: int


class PositionRecord(BaseModel):
    position: str
    games: int
    wins: int


class RatingPoint(BaseModel):
    match_id: int
    played_at: datetime
    won: bool
    rating_after: float
    delta: float


class RecentMatch(BaseModel):
    match_id: int
    played_at: datetime
    won: bool
    position: str
    # None for matches recorded before rating changes were kept.
    delta: Optional[float]
    ai_mvp: bool
    user_mvp: bool
    teammates: list[str]


class PlayerRecordDetail(BaseModel):
    record: PlayerRecord
    positions: list[PositionRecord]
    rating_history: list[RatingPoint]
    recent: list[RecentMatch]


@router.get("/records", response_model=list[PlayerRecord])
def player_records(server_id: int, db: Session = Depends(get_db)) -> list[PlayerRecord]:
    """Leaderboard rows: Final Rating plus win/loss and MVP counts."""
    return [PlayerRecord(**row) for row in StatsService(db, server_id).records()]


@router.get("/players/{player_id}/record", response_model=PlayerRecordDetail)
def player_record(server_id: int, player_id: int, db: Session = Depends(get_db)) -> PlayerRecordDetail:
    return PlayerRecordDetail(**StatsService(db, server_id).player_record(player_id))
