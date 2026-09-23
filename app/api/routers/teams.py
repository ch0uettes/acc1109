from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_actor, get_db
from app.balance.config import HardConstraintConfig, NormalizationConfig
from app.balance.constraints import HardConstraintLayer
from app.balance.execution_context import ExecutionContext
from app.balance.result import BalanceResult
from app.balance.strategy import STRATEGY_REGISTRY
from app.database.repositories.decision_log_repository import DecisionLogRepository
from app.models.decision_log import (
    DecisionLogEntry,
    FeatureContributionSnapshot,
    PlayerSnapshot,
    RecommendationSnapshot,
    SearchStatisticsSnapshot,
    VersionMetadataSnapshot,
)
from app.models.server_membership import ServerMembership
from app.models.team import SavedTeam, Team
from app.position.schemas import RolePreference
from app.position.signup import PlayerSignup
from app.roster_export import saved_teams_to_txt, saved_teams_to_xlsx_bytes
from app.services.player_service import PlayerService
from app.services.server_service import ServerService
from app.services.team_service import TeamService

router = APIRouter(prefix="/servers/{server_id}/teams", tags=["teams"])

STRATEGY_CHOICES = tuple(STRATEGY_REGISTRY.keys())


class SignupOverride(BaseModel):
    player_id: int
    match_override: Optional[RolePreference] = None
    enforce_fixed_role: bool = True


class GenerateTeamsRequest(BaseModel):
    player_ids: list[int]
    overrides: list[SignupOverride] = []
    k: int = 3
    strategy: str = "stable"


class DecisionLogDraft(BaseModel):
    """Everything TeamService.log_decision() needs to persist a Decision
    Log entry, minus the fields only known once the operator picks a combo
    (chosen_rank/reason) - the API is stateless across the
    generate -> (operator picks one) -> save round trip, so the client
    echoes this straight back on /save instead of the server holding the
    in-memory ExecutionContext Streamlit's st.session_state used to."""

    execution_id: Optional[str] = None
    strategy_name: str
    search_policy_name: Optional[str] = None
    player_ids: list[int]
    player_snapshot: list[PlayerSnapshot] = []
    search_statistics: Optional[SearchStatisticsSnapshot] = None
    version_metadata: Optional[VersionMetadataSnapshot] = None
    execution_time_seconds: Optional[float] = None
    candidate_count: Optional[int] = None
    recommendations: list[RecommendationSnapshot]


class GenerateTeamsResponse(BaseModel):
    results: list[BalanceResult]
    decision_log_draft: DecisionLogDraft


class SaveTeamsRequest(BaseModel):
    teams: list[Team]
    decision_log_draft: Optional[DecisionLogDraft] = None
    chosen_rank: int = 1
    reason: Optional[str] = None


def _service(server_id: int, db: Session) -> TeamService:
    return TeamService(db, server_id)


def _team_service_for_strategy(server_id: int, db: Session, strategy_key: str) -> TeamService:
    if strategy_key not in STRATEGY_REGISTRY:
        raise HTTPException(status_code=400, detail=f"Unknown strategy '{strategy_key}' - choose one of {STRATEGY_CHOICES}")
    server = ServerService(db).get_server(server_id)
    return TeamService(
        db,
        server_id,
        strategy=STRATEGY_REGISTRY[strategy_key](),
        normalization_config=server.normalization_config if server else None,
        hard_constraints=HardConstraintLayer(server.hard_constraint_config) if server else None,
        constraint_priorities=server.constraint_priorities if server else None,
    )


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


def _build_decision_log_draft(context: ExecutionContext) -> DecisionLogDraft:
    """Same field mapping as TeamService.log_decision() - kept in sync by
    hand since the API round-trips this through the client rather than
    calling log_decision() directly on a live ExecutionContext (see
    DecisionLogDraft's docstring)."""
    return DecisionLogDraft(
        execution_id=context.input.execution_id,
        strategy_name=context.input.strategy.name,
        search_policy_name=context.input.search_policy.name,
        player_ids=[player.id for player in context.input.player_profiles],
        player_snapshot=[
            PlayerSnapshot(
                id=player.id,
                nickname=player.nickname,
                tier=player.tier,
                division=player.division,
                main_role=player.main_role,
                sub_role=player.sub_role,
                final_rating=player.final_rating,
                internal_rating=player.internal_rating,
                confidence=player.confidence,
            )
            for player in context.input.player_profiles
        ],
        search_statistics=(
            SearchStatisticsSnapshot(
                nodes_expanded=context.runtime.search_statistics.nodes_expanded,
                elapsed_seconds=context.runtime.search_statistics.elapsed_seconds,
                candidate_count=context.runtime.search_statistics.candidate_count,
                node_budget_hit=context.runtime.search_statistics.node_budget_hit,
                time_budget_hit=context.runtime.search_statistics.time_budget_hit,
            )
            if context.runtime.search_statistics
            else None
        ),
        version_metadata=VersionMetadataSnapshot(
            app_version=context.input.version_metadata.app_version,
            strategy_name=context.input.version_metadata.strategy_name,
            search_policy_name=context.input.version_metadata.search_policy_name,
            feature_weights=context.input.version_metadata.feature_weights,
        ),
        execution_time_seconds=(
            context.runtime.search_statistics.elapsed_seconds if context.runtime.search_statistics else None
        ),
        candidate_count=len(context.runtime.candidate_teams),
        recommendations=[
            RecommendationSnapshot(
                rank=i + 1,
                cost=result.cost,
                team_player_ids=[[p.id for p in team.players] for team in result.teams],
                contributions=[
                    FeatureContributionSnapshot(
                        name=c.name,
                        raw=c.raw,
                        normalized=c.normalized,
                        weight=c.weight,
                        contribution=c.contribution,
                        contribution_pct=c.contribution_pct,
                    )
                    for c in result.contributions
                ],
            )
            for i, result in enumerate(context.runtime.candidate_teams)
        ],
    )


@router.post("/generate", response_model=GenerateTeamsResponse)
def generate_top_teams(
    server_id: int, payload: GenerateTeamsRequest, db: Session = Depends(get_db)
) -> GenerateTeamsResponse:
    signups = _build_signups(server_id, db, payload)
    service = _team_service_for_strategy(server_id, db, payload.strategy)
    context = service.run(signups, k=payload.k)
    return GenerateTeamsResponse(
        results=context.runtime.candidate_teams,
        decision_log_draft=_build_decision_log_draft(context),
    )


@router.post("/save", response_model=list[int])
def save_generated_teams(
    server_id: int,
    payload: SaveTeamsRequest,
    db: Session = Depends(get_db),
    actor: ServerMembership = Depends(get_actor),
) -> list[int]:
    result = BalanceResult(teams=payload.teams, cost=0.0)
    team_ids = _service(server_id, db).save_generated_teams(result, actor.role)

    if payload.decision_log_draft is not None:
        now = datetime.utcnow()
        entry = DecisionLogEntry(
            server_id=server_id,
            created_at=now,
            chosen_rank=payload.chosen_rank,
            chosen_at=now,
            reason=payload.reason,
            **payload.decision_log_draft.model_dump(),
        )
        try:
            DecisionLogRepository(db, server_id).add(entry)
        except Exception:
            # Same "team save already committed, decision log is
            # best-effort" contract as TeamService.log_decision()'s
            # Streamlit caller - never fail the save over this.
            pass

    return team_ids


@router.get("/runs", response_model=list[str])
def list_saved_runs(server_id: int, limit: int = 20, db: Session = Depends(get_db)) -> list[str]:
    return [dt.isoformat() for dt in _service(server_id, db).list_saved_runs(limit=limit)]


@router.get("/runs/{generated_at}", response_model=list[SavedTeam])
def load_saved_run(server_id: int, generated_at: str, db: Session = Depends(get_db)) -> list[SavedTeam]:
    return _service(server_id, db).load_saved_run(datetime.fromisoformat(generated_at))


@router.get("/runs/{generated_at}/export.txt")
def export_saved_run_txt(server_id: int, generated_at: str, db: Session = Depends(get_db)) -> Response:
    saved_teams = _service(server_id, db).load_saved_run(datetime.fromisoformat(generated_at))
    return Response(
        content=saved_teams_to_txt(saved_teams),
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="team_{generated_at}.txt"'},
    )


@router.get("/runs/{generated_at}/export.xlsx")
def export_saved_run_xlsx(server_id: int, generated_at: str, db: Session = Depends(get_db)) -> Response:
    saved_teams = _service(server_id, db).load_saved_run(datetime.fromisoformat(generated_at))
    return Response(
        content=saved_teams_to_xlsx_bytes(saved_teams),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="team_{generated_at}.xlsx"'},
    )
