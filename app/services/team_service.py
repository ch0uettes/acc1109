from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.balance.balancer import TeamBalancer
from app.balance.config import NormalizationConfig
from app.balance.constraints import HardConstraintLayer
from app.balance.result import BalanceResult
from app.balance.strategy import IBalanceStrategy
from app.database.repositories.decision_log_repository import DecisionLogRepository
from app.database.repositories.team_repository import TeamRepository
from app.models.decision_log import DecisionLogEntry, FeatureContributionSnapshot, RecommendationSnapshot
from app.position.signup import PlayerSignup
from app.services.rbac import Permission, require_permission
from app.utils.enums import Role


class TeamService:
    def __init__(
        self,
        session: Session,
        server_id: int,
        balancer: TeamBalancer | None = None,
        strategy: IBalanceStrategy | None = None,
        normalization_config: NormalizationConfig | None = None,
        hard_constraints: HardConstraintLayer | None = None,
    ) -> None:
        self.server_id = server_id
        self.repo = TeamRepository(session, server_id)
        self.decision_log_repo = DecisionLogRepository(session, server_id)
        self.balancer = balancer or TeamBalancer(
            strategy=strategy, normalization_config=normalization_config, hard_constraints=hard_constraints
        )

    def generate_teams(self, signups: list[PlayerSignup]) -> BalanceResult:
        return self.balancer.generate_teams(signups)

    def generate_top_teams(self, signups: list[PlayerSignup], k: int = 3) -> list[BalanceResult]:
        return self.balancer.generate_top_teams(signups, k=k)

    def save_generated_teams(self, result: BalanceResult, actor_role: Role) -> list[int]:
        """Unlike generate_teams()/generate_top_teams() (pure computation,
        no DB write), this persists rosters - same permission tier as
        MatchService.record_match(), since saving a team split is part of
        setting up a match, not a base-level action every Player gets."""
        require_permission(actor_role, Permission.CREATE_MATCH)
        return self.repo.save_generated_teams(result.teams)

    def log_decision(
        self,
        signups: list[PlayerSignup],
        strategy_name: str,
        results: list[BalanceResult],
        chosen_rank: int,
        reason: str | None = None,
    ) -> DecisionLogEntry:
        """Records what the AI offered (every combo it recommended, with
        full Feature contribution breakdowns) and which one the operator
        actually chose. chosen_rank != 1 means the operator overrode the
        AI's own top pick - that disagreement is the Human Feedback
        signal v2.0's AI Learning Engine will eventually train against.
        No permission check of its own - this only ever runs as a
        side-effect of an already-permitted save_generated_teams() call."""
        now = datetime.utcnow()
        entry = DecisionLogEntry(
            server_id=self.server_id,
            created_at=now,
            strategy_name=strategy_name,
            player_ids=[signup.player.id for signup in signups],
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
                for i, result in enumerate(results)
            ],
            chosen_rank=chosen_rank,
            chosen_at=now,
            reason=reason,
        )
        return self.decision_log_repo.add(entry)

    def recent_decisions(self, limit: int = 20) -> list[DecisionLogEntry]:
        return self.decision_log_repo.list_for_server(limit=limit)
