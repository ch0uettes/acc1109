from __future__ import annotations

from abc import ABC, abstractmethod
from itertools import permutations
from typing import Optional

from app.balance.config import DEFAULT_ROLE_PENALTY_CONFIG, RolePenaltyConfig
from app.models.player import Player
from app.models.team import TeamSlot
from app.position.schemas import RolePreference
from app.utils.enums import Position

ALL_POSITIONS = list(Position)


class PositionAssigner(ABC):
    """Explores possible lane assignments for one team of len(Position)
    players, enforcing Main-first/Sub-then/Other-last-resort. Doesn't know
    how `preferences` were resolved (RolePreferenceManager's job) or how
    the resulting slots get scored (BalanceEvaluator's job)."""

    @abstractmethod
    def assign(
        self,
        players: list[Player],
        preferences: dict[int, RolePreference],
        forced_positions: Optional[dict[int, Position]] = None,
    ) -> list[TeamSlot]:
        ...


class BipartiteMatchingPositionAssigner(PositionAssigner):
    """Enumerates every position permutation (len(Position)! = 120 - cheap
    at this size, no real matching algorithm needed). First pass is
    restricted to each player's {main, sub} set - if any permutation
    survives that filter, Other is structurally excluded from the
    candidate pool entirely (the hard constraint). Only if zero survive
    does a second pass open up the full position set (a complete graph,
    so a bijection always exists)."""

    def __init__(self, role_penalty_config: RolePenaltyConfig = DEFAULT_ROLE_PENALTY_CONFIG) -> None:
        self.role_penalty_config = role_penalty_config

    def assign(
        self,
        players: list[Player],
        preferences: dict[int, RolePreference],
        forced_positions: Optional[dict[int, Position]] = None,
    ) -> list[TeamSlot]:
        if len(players) != len(ALL_POSITIONS):
            raise ValueError(
                f"PositionAssigner requires exactly {len(ALL_POSITIONS)} players, got {len(players)}"
            )
        # Sort by id so permutations() - and therefore which of several
        # equal-cost assignments wins - is deterministic regardless of the
        # caller's input order.
        ordered_players = sorted(players, key=lambda p: p.id)
        forced = forced_positions or {}

        # A this-match Fixed Role override (see FixedRoleConstraint) must
        # actually be pinned here, at assignment time - otherwise this
        # optimizer, which only ever minimizes *total* roster cost, is
        # free to bump the forced player to a different lane whenever
        # someone else on the same roster also wants their position, and
        # the search engine would then have to reject the entire roster
        # after the fact. Pinning here means almost every roster
        # containing the forced player satisfies the requirement
        # immediately, instead of only the rare roster where honoring it
        # happens to also be the cost-minimal choice.
        if forced:
            pinned = self._best_assignment(ordered_players, preferences, restrict_to_main_sub=True, forced=forced)
            if pinned is not None:
                return pinned
            pinned_full = self._best_assignment(ordered_players, preferences, restrict_to_main_sub=False, forced=forced)
            if pinned_full is not None:
                return pinned_full
            # Structurally impossible to honor every pin at once (e.g. two
            # forced players on the same roster both requiring the same
            # position) - fall through to the unforced best-fit below so a
            # valid, fully-evaluated roster is still returned. Leaving the
            # pins unsatisfied here is exactly what FixedRoleConstraint
            # exists to catch and reject at leaf time.

        restricted = self._best_assignment(ordered_players, preferences, restrict_to_main_sub=True)
        if restricted is not None:
            return restricted

        full = self._best_assignment(ordered_players, preferences, restrict_to_main_sub=False)
        assert full is not None, "the full position set is a complete graph - a bijection always exists"
        return full

    def _best_assignment(
        self,
        players: list[Player],
        preferences: dict[int, RolePreference],
        restrict_to_main_sub: bool,
        forced: Optional[dict[int, Position]] = None,
    ) -> Optional[list[TeamSlot]]:
        forced = forced or {}
        best: Optional[list[tuple[Player, Position, float, str]]] = None
        best_cost: Optional[float] = None

        for perm in permutations(ALL_POSITIONS):
            assignment: list[tuple[Player, Position, float, str]] = []
            total_cost = 0.0
            valid = True
            for player, position in zip(players, perm):
                required = forced.get(player.id)
                if required is not None and position != required:
                    valid = False
                    break
                penalty, source = self._penalty_for(preferences[player.id], position)
                if restrict_to_main_sub and source == "other":
                    valid = False
                    break
                assignment.append((player, position, penalty, source))
                total_cost += penalty
            if not valid:
                continue
            if best_cost is None or total_cost < best_cost:
                best, best_cost = assignment, total_cost

        if best is None:
            return None
        return [
            TeamSlot(position=position, player=player, role_penalty=penalty, role_source=source)
            for player, position, penalty, source in best
        ]

    def _penalty_for(self, preference: RolePreference, position: Position) -> tuple[float, str]:
        if position == preference.main:
            return self.role_penalty_config.main, "main"
        if preference.sub is not None and position == preference.sub:
            return self.role_penalty_config.sub, "sub"
        return self.role_penalty_config.other, "other"
