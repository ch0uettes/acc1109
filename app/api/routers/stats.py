from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.match import Match
from app.models.player import Player
from app.services.stats_service import StatsService

router = APIRouter(prefix="/servers/{server_id}/stats", tags=["stats"])


@router.get("/leaderboard", response_model=list[Player])
def leaderboard(server_id: int, db: Session = Depends(get_db)) -> list[Player]:
    return StatsService(db, server_id).leaderboard()


@router.get("/players/{player_id}/matches", response_model=list[Match])
def player_match_history(server_id: int, player_id: int, db: Session = Depends(get_db)) -> list[Match]:
    return StatsService(db, server_id).player_match_history(player_id)


@router.get("/ai-mvp-accuracy", response_model=float)
def ai_mvp_accuracy(server_id: int, db: Session = Depends(get_db)) -> float:
    return StatsService(db, server_id).ai_mvp_accuracy()
