from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.ai.contribution import OCRContributionScoreCalculator
from app.api.deps import get_actor, get_db
from app.models.match import Match
from app.models.server_membership import ServerMembership
from app.models.team import Team, TeamSlot
from app.services.match_service import MatchService
from app.services.team_service import TeamService

router = APIRouter(prefix="/servers/{server_id}/matches", tags=["matches"], dependencies=[Depends(get_actor)])


class PlayerStats(BaseModel):
    kills: int = 0
    deaths: int = 0
    assists: int = 0
    cs: int = 0
    gold: int = 0
    damage: int = 0
    vision_score: int = 0


class RecordMatchRequest(BaseModel):
    # Either a saved team run (the normal path: the server rebuilds the teams
    # from it) or the teams themselves.
    team_run_at: Optional[datetime] = None
    teams: Optional[list[Team]] = None
    winning_team_index: int
    note: Optional[str] = None
    match_stats_by_player_id: dict[int, PlayerStats] = {}


class DeleteMatchResponse(BaseModel):
    ratings_reverted: bool


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
    if payload.team_run_at is not None:
        teams = _teams_from_run(server_id, db, payload.team_run_at)
    elif payload.teams:
        teams = payload.teams
    else:
        raise HTTPException(status_code=400, detail="저장된 팀(team_run_at)이나 팀 구성(teams)이 필요합니다")
    stats_by_id = {pid: stats.model_dump() for pid, stats in payload.match_stats_by_player_id.items()}
    calculator = OCRContributionScoreCalculator() if stats_by_id else None
    return _service(server_id, db, calculator).record_match(
        teams=teams,
        winning_team_index=payload.winning_team_index,
        actor_role=actor.role,
        note=payload.note,
        match_stats_by_player_id=stats_by_id,
        team_run_at=payload.team_run_at,
    )


def _teams_from_run(server_id: int, db: Session, team_run_at: datetime) -> list[Team]:
    saved = TeamService(db, server_id).load_saved_run(team_run_at)
    if not saved:
        raise HTTPException(status_code=404, detail="저장된 팀을 찾을 수 없습니다")
    teams = []
    for saved_team in saved:
        if any(entry.player is None for entry in saved_team.entries):
            raise HTTPException(status_code=400, detail="저장된 팀에 더 이상 존재하지 않는 참가자가 있습니다")
        teams.append(
            Team(
                index=saved_team.index,
                players=[entry.player for entry in saved_team.entries],
                slots=[
                    TeamSlot(position=entry.position, player=entry.player, role_penalty=0.0, role_source="main")
                    for entry in saved_team.entries
                ],
            )
        )
    return teams


@router.get("", response_model=list[Match])
def list_matches(server_id: int, limit: int = 50, db: Session = Depends(get_db)) -> list[Match]:
    return _service(server_id, db).list_recent(limit=min(limit, 200))


@router.get("/pending-votes", response_model=list[Match])
def list_pending_votes(server_id: int, db: Session = Depends(get_db)) -> list[Match]:
    return _service(server_id, db).list_pending_votes()


@router.get("/{match_id}", response_model=Match)
def get_match(server_id: int, match_id: int, db: Session = Depends(get_db)) -> Match:
    match = _service(server_id, db).get_match(match_id)
    if match is None:
        raise HTTPException(status_code=404, detail="Match not found")
    return match


@router.delete("/{match_id}", response_model=DeleteMatchResponse)
def delete_match(
    server_id: int,
    match_id: int,
    db: Session = Depends(get_db),
    actor: ServerMembership = Depends(get_actor),
) -> DeleteMatchResponse:
    return DeleteMatchResponse(ratings_reverted=_service(server_id, db).delete_match(match_id, actor.role))


@router.post("/{match_id}/user-mvp", status_code=204)
def set_user_mvp(
    server_id: int,
    match_id: int,
    payload: SetUserMvpRequest,
    db: Session = Depends(get_db),
    actor: ServerMembership = Depends(get_actor),
) -> None:
    _service(server_id, db).set_user_mvp(match_id, payload.player_id, actor.role)
