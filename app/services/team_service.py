from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.balance.balancer import TeamBalancer
from app.balance.config import NormalizationConfig
from app.balance.constraints import HardConstraintLayer
from app.balance.execution_context import ExecutionContext
from app.balance.result import BalanceResult
from app.balance.strategy import IBalanceStrategy
from app.database.repositories.decision_log_repository import DecisionLogRepository
from app.database.repositories.team_repository import TeamRepository
from app.models.decision_log import (
    DecisionLogEntry,
    FeatureContributionSnapshot,
    PlayerSnapshot,
    RecommendationSnapshot,
    SearchStatisticsSnapshot,
    VersionMetadataSnapshot,
)
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
        constraint_priorities: dict[str, int] | None = None,
    ) -> None:
        self.server_id = server_id
        self.repo = TeamRepository(session, server_id)
        self.decision_log_repo = DecisionLogRepository(session, server_id)
        self.balancer = balancer or TeamBalancer(
            strategy=strategy,
            normalization_config=normalization_config,
            hard_constraints=hard_constraints,
            constraint_priorities=constraint_priorities,
        )

    def generate_teams(self, signups: list[PlayerSignup]) -> BalanceResult:
        return self.balancer.generate_teams(signups)

    def generate_top_teams(self, signups: list[PlayerSignup], k: int = 3) -> list[BalanceResult]:
        return self.balancer.generate_top_teams(signups, k=k)

    def run(self, signups: list[PlayerSignup], k: int = 3) -> ExecutionContext:
        """Same search as generate_top_teams(), but returns the whole
        ExecutionContext (search stats, feature snapshots, version
        metadata, ...) instead of just the candidate list - what
        log_decision() needs to persist the full v1.0 Decision Log
        schema. UI code that only wants to display combos can keep using
        generate_top_teams(); code that will later call log_decision()
        should call this instead and hang onto the returned context."""
        return self.balancer.run(signups, k=k)

    def save_generated_teams(self, result: BalanceResult, actor_role: Role) -> list[int]:
        """Unlike generate_teams()/generate_top_teams() (pure computation,
        no DB write), this persists rosters - same permission tier as
        MatchService.record_match(), since saving a team split is part of
        setting up a match, not a base-level action every Player gets."""
        require_permission(actor_role, Permission.CREATE_MATCH)
        return self.repo.save_generated_teams(result.teams)

    def log_decision(self, context: ExecutionContext, chosen_rank: int, reason: str | None = None) -> DecisionLogEntry:
        """Records everything one AI run produced (candidates, Feature
        snapshots, search stats, version metadata, a frozen snapshot of
        each player as they were at execution time) and which
        recommendation the operator actually chose. chosen_rank != 1
        means the operator overrode the AI's own top pick - that
        disagreement is the Human Feedback signal v2.0's AI Learning
        Engine will eventually train against. No permission check of its
        own - this only ever runs as a side-effect of an
        already-permitted save_generated_teams() call."""
        now = datetime.utcnow()
        entry = DecisionLogEntry(
            server_id=self.server_id,
            execution_id=context.input.execution_id,
            created_at=now,
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
            chosen_rank=chosen_rank,
            chosen_at=now,
            reason=reason,
        )
        return self.decision_log_repo.add(entry)

    def recent_decisions(self, limit: int = 20) -> list[DecisionLogEntry]:
        return self.decision_log_repo.list_for_server(limit=limit)
