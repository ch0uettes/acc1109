from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_actor, get_db
from app.balance.result import BalanceResult
from app.models.server_membership import ServerMembership
from app.models.team import SavedTeam, Team
from app.position.schemas import RolePreference
from app.position.signup import PlayerSignup
from app.services.player_service import PlayerService
from app.services.team_service import TeamService

router = APIRouter(prefix="/servers/{server_id}/teams", tags=["teams"])


class SignupOverride(BaseModel):
    player_id: int
    match_override: Optional[RolePreference] = None
    enforce_fixed_role: bool = True


class GenerateTeamsRequest(BaseModel):
    player_ids: list[int]
    overrides: list[SignupOverride] = []
    k: int = 3


class SaveTeamsRequest(BaseModel):
    teams: list[Team]


def _service(server_id: int, db: Session) -> TeamService:
    return TeamService(db, server_id)


def _build_signups(server_id: int, db: Session, payload: GenerateTeamsRequest) -> list[PlayerSignup]:
    players_by_id = {p.id: p for p in PlayerService(db, server_id).list_players()}
    overrides_by_id = {o.player_id: o for o in payload.overrides}
    signups = []
    for player_id in payload.player_ids:
        player = players_by_id[player_id]
        override = overrides_by_id.get(player_id)
        signups.append(
            PlayerSignup(
                player=player,
                match_override=override.match_override if override else None,
                enforce_fixed_role=override.enforce_fixed_role if override else True,
            )
        )
    return signups


@router.post("/generate", response_model=list[BalanceResult])
def generate_top_teams(
    server_id: int, payload: GenerateTeamsRequest, db: Session = Depends(get_db)
) -> list[BalanceResult]:
    signups = _build_signups(server_id, db, payload)
    return _service(server_id, db).generate_top_teams(signups, k=payload.k)


@router.post("/save", response_model=list[int])
def save_generated_teams(
    server_id: int,
    payload: SaveTeamsRequest,
    db: Session = Depends(get_db),
    actor: ServerMembership = Depends(get_actor),
) -> list[int]:
    result = BalanceResult(teams=payload.teams, cost=0.0)
    return _service(server_id, db).save_generated_teams(result, actor.role)


@router.get("/runs", response_model=list[str])
def list_saved_runs(server_id: int, limit: int = 20, db: Session = Depends(get_db)) -> list[str]:
    return [dt.isoformat() for dt in _service(server_id, db).list_saved_runs(limit=limit)]


@router.get("/runs/{generated_at}", response_model=list[SavedTeam])
def load_saved_run(server_id: int, generated_at: str, db: Session = Depends(get_db)) -> list[SavedTeam]:
    return _service(server_id, db).load_saved_run(datetime.fromisoformat(generated_at))
