from __future__ import annotations

from types import MappingProxyType
from typing import Optional

from app.balance.constraint_engine.context import ConstraintContext
from app.balance.search_policy import SearchPolicy
from app.balance.strategy import IBalanceStrategy
from app.models.player import Player
from app.models.team import Team, TeamSlot
from app.position.schemas import RolePreference

# Copy cache type: id(live Player) -> its one deep copy for this context build.
_PlayerCopyCache = dict


def _copy_player(player: Player, cache: _PlayerCopyCache) -> Player:
    """Player is a plain (non-frozen) Pydantic model shared by reference
    everywhere else in the search - wrapping ConstraintContext's outer
    tuple/MappingProxyType containers alone doesn't stop a plugin from
    mutating a Player's fields in place (e.g. `context.candidate_player.tier
    = x`), which would silently corrupt the live search's own state since
    nothing here would otherwise copy it. deep-copying at the context
    boundary means a plugin can only ever mutate its own throwaway copy.

    Cached by `id()` per context build: the same live Player instance is
    typically reachable from 2-3 fields at once (player_profiles,
    roster/team.players, team.slots[*].player) - copying it once and
    reusing that copy everywhere it's referenced, instead of a fresh
    independent deepcopy per reference, is the difference between ~1 and
    ~3 deepcopies per player per leaf visited."""
    key = id(player)
    copied = cache.get(key)
    if copied is None:
        copied = player.model_copy(deep=True)
        cache[key] = copied
    return copied


def _copy_team(team: Team, cache: _PlayerCopyCache) -> Team:
    """Rebuilds Team/TeamSlot (also plain Pydantic models) around
    _copy_player()'s cached copies, rather than Team.model_copy(deep=True)
    - the latter would deepcopy `players` and `slots[*].player`
    independently, duplicating work for the same underlying player and
    silently dropping the object-identity aliasing between the two."""
    copied_slots = (
        [
            TeamSlot(
                position=slot.position,
                player=_copy_player(slot.player, cache),
                role_penalty=slot.role_penalty,
                role_source=slot.role_source,
            )
            for slot in team.slots
        ]
        if team.slots is not None
        else None
    )
    return Team(
        index=team.index,
        players=[_copy_player(p, cache) for p in team.players],
        slots=copied_slots,
    )


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
        cache: _PlayerCopyCache = {}
        return ConstraintContext(
            rosters=tuple(tuple(_copy_player(p, cache) for p in roster) for roster in rosters),
            team_index=team_index,
            candidate_player=_copy_player(player, cache),
            teams=None,
            player_profiles=tuple(_copy_player(p, cache) for p in player_profiles),
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
        cache: _PlayerCopyCache = {}
        frozen_teams = tuple(_copy_team(team, cache) for team in teams)
        return ConstraintContext(
            rosters=tuple(tuple(team.players) for team in frozen_teams),
            team_index=None,
            candidate_player=None,
            teams=frozen_teams,
            player_profiles=tuple(_copy_player(p, cache) for p in player_profiles),
            role_preferences=MappingProxyType(dict(role_preferences)),
            strategy=strategy,
            search_policy=search_policy,
            constraint_priorities=MappingProxyType(dict(constraint_priorities or {})),
            override_player_ids=override_player_ids,
        )


DEFAULT_CONSTRAINT_CONTEXT_FACTORY = ConstraintContextFactory()
