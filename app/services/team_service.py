from __future__ import annotations

from sqlalchemy.orm import Session

from app.balance.balancer import TeamBalancer
from app.balance.config import NormalizationConfig
from app.balance.constraints import HardConstraintLayer
from app.balance.result import BalanceResult
from app.balance.strategy import IBalanceStrategy
from app.database.repositories.team_repository import TeamRepository
from app.position.signup import PlayerSignup


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

    def save_generated_teams(self, result: BalanceResult) -> list[int]:
        return self.repo.save_generated_teams(result.teams)
