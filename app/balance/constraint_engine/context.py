from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Optional

from app.balance.search_policy import SearchPolicy
from app.balance.strategy import IBalanceStrategy
from app.models.player import Player
from app.models.team import Team
from app.position.schemas import RolePreference


@dataclass(frozen=True)
class ConstraintContext:
    """Read-only view a Constraint plugin receives - never ExecutionContext,
    never a mutable reference to the search engine's live rosters. Built
    exclusively by ConstraintContextFactory, which wraps every collection
    field in an immutable container (tuple / MappingProxyType) so a plugin
    calling .append()/.sort()/.clear() on any field fails at the Python
    level, not just violates a docstring.

    One shape for both partial (mid-DFS) and leaf checks - which fields
    are populated depends on which factory method built it:
    - Partial: rosters/team_index/candidate_player set, teams=None.
    - Leaf: teams set (complete Team objects w/ slots), team_index/
      candidate_player=None."""

    rosters: tuple[tuple[Player, ...], ...]
    team_index: Optional[int]
    candidate_player: Optional[Player]
    teams: Optional[tuple[Team, ...]]
    player_profiles: tuple[Player, ...]
    role_preferences: MappingProxyType[int, RolePreference]
    strategy: IBalanceStrategy
    search_policy: SearchPolicy
    constraint_priorities: MappingProxyType[str, int]
    # Player ids whose RolePreference came from an explicit this-match
    # match_override (see PlayerSignup), NOT from their stored profile
    # main/sub role - RolePreferenceManager.resolve() erases that
    # distinction once it produces role_preferences, so it has to be
    # threaded separately for FixedRoleConstraint to know which players
    # actually need their position enforced as a hard requirement rather
    # than every player's ordinary preferred lane. Empty for partial
    # contexts (no PartialHardConstraint plugin needs this yet).
    override_player_ids: frozenset[int] = frozenset()
