from __future__ import annotations

from types import MappingProxyType
from typing import Optional

from app.balance.constraint_engine.context import ConstraintContext
from app.balance.search_policy import SearchPolicy
from app.balance.strategy import IBalanceStrategy
from app.models.player import Player
from app.models.team import Team
from app.position.schemas import RolePreference


class ConstraintContextFactory:
    """The only place a ConstraintContext gets built. ConstraintExecutor
    only ever *requests* a context through this factory, never constructs
    one inline - this is what lets a future TournamentContextFactory /
    DraftContextFactory / ReplayContextFactory / SimulationContextFactory
    subclass and enrich context-building (e.g. injecting bracket/round
    metadata) without ConstraintExecutor, or anything downstream of it,
    changing at all."""

    def create_partial_context(
        self,
        rosters: list[list[Player]],
        team_index: int,
        player: Player,
        player_profiles: list[Player],
        role_preferences: dict[int, RolePreference],
        strategy: IBalanceStrategy,
        search_policy: SearchPolicy,
        constraint_priorities: Optional[dict[str, int]] = None,
    ) -> ConstraintContext:
        return ConstraintContext(
            rosters=tuple(tuple(roster) for roster in rosters),
            team_index=team_index,
            candidate_player=player,
            teams=None,
            player_profiles=tuple(player_profiles),
            role_preferences=MappingProxyType(dict(role_preferences)),
            strategy=strategy,
            search_policy=search_policy,
            constraint_priorities=MappingProxyType(dict(constraint_priorities or {})),
        )

    def create_leaf_context(
        self,
        teams: list[Team],
        player_profiles: list[Player],
        role_preferences: dict[int, RolePreference],
        strategy: IBalanceStrategy,
        search_policy: SearchPolicy,
        constraint_priorities: Optional[dict[str, int]] = None,
        override_player_ids: frozenset = frozenset(),
    ) -> ConstraintContext:
        return ConstraintContext(
            rosters=tuple(tuple(team.players) for team in teams),
            team_index=None,
            candidate_player=None,
            teams=tuple(teams),
            player_profiles=tuple(player_profiles),
            role_preferences=MappingProxyType(dict(role_preferences)),
            strategy=strategy,
            search_policy=search_policy,
            constraint_priorities=MappingProxyType(dict(constraint_priorities or {})),
            override_player_ids=override_player_ids,
        )


DEFAULT_CONSTRAINT_CONTEXT_FACTORY = ConstraintContextFactory()
