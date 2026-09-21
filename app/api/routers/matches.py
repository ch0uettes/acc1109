from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.ai.contribution import OCRContributionScoreCalculator
from app.api.deps import get_actor, get_db
from app.models.match import Match
from app.models.server_membership import ServerMembership
from app.models.team import Team
from app.services.match_service import MatchService

router = APIRouter(prefix="/servers/{server_id}/matches", tags=["matches"])


class PlayerStats(BaseModel):
    kills: int = 0
    deaths: int = 0
    assists: int = 0
    cs: int = 0
    gold: int = 0
    damage: int = 0
    vision_score: int = 0


class RecordMatchRequest(BaseModel):
    teams: list[Team]
    winning_team_index: int
    note: Optional[str] = None
    match_stats_by_player_id: dict[int, PlayerStats] = {}


class SetUserMvpRequest(BaseModel):
    player_id: int


def _service(server_id: int, db: Session, contribution_calculator=None) -> MatchService:
    return MatchService(db, server_id, contribution_calculator=contribution_calculator)


@router.post("", response_model=Match)
def record_match(
    server_id: int,
    payload: RecordMatchRequest,
    db: Session = Depends(get_db),
    actor: ServerMembership = Depends(get_actor),
) -> Match:
    stats_by_id = {pid: stats.model_dump() for pid, stats in payload.match_stats_by_player_id.items()}
    calculator = OCRContributionScoreCalculator() if stats_by_id else None
    return _service(server_id, db, calculator).record_match(
        teams=payload.teams,
        winning_team_index=payload.winning_team_index,
        actor_role=actor.role,
        note=payload.note,
        match_stats_by_player_id=stats_by_id,
    )


@router.get("/pending-votes", response_model=list[Match])
def list_pending_votes(server_id: int, db: Session = Depends(get_db)) -> list[Match]:
    return _service(server_id, db).list_pending_votes()


@router.get("/{match_id}", response_model=Match)
def get_match(server_id: int, match_id: int, db: Session = Depends(get_db)) -> Match:
    match = _service(server_id, db).get_match(match_id)
    if match is None:
        raise HTTPException(status_code=404, detail="Match not found")
    return match


@router.post("/{match_id}/user-mvp", status_code=204)
def set_user_mvp(
    server_id: int,
    match_id: int,
    payload: SetUserMvpRequest,
    db: Session = Depends(get_db),
    actor: ServerMembership = Depends(get_actor),
) -> None:
    _service(server_id, db).set_user_mvp(match_id, payload.player_id, actor.role)
