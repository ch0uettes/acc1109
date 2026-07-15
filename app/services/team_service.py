from __future__ import annotations

from sqlalchemy.orm import Session

from app.balance.balancer import TeamBalancer
from app.balance.config import NormalizationConfig
from app.balance.constraints import HardConstraintLayer
from app.balance.result import BalanceResult
from app.balance.strategy import IBalanceStrategy
from app.database.repositories.team_repository import TeamRepository
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
        self.repo = TeamRepository(session, server_id)
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
