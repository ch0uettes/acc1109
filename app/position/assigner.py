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
    def assign(self, players: list[Player], preferences: dict[int, RolePreference]) -> list[TeamSlot]:
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

    def assign(self, players: list[Player], preferences: dict[int, RolePreference]) -> list[TeamSlot]:
        if len(players) != len(ALL_POSITIONS):
            raise ValueError(
                f"PositionAssigner requires exactly {len(ALL_POSITIONS)} players, got {len(players)}"
            )
        # Sort by id so permutations() - and therefore which of several
        # equal-cost assignments wins - is deterministic regardless of the
        # caller's input order.
        ordered_players = sorted(players, key=lambda p: p.id)

        restricted = self._best_assignment(ordered_players, preferences, restrict_to_main_sub=True)
        if restricted is not None:
            return restricted

        full = self._best_assignment(ordered_players, preferences, restrict_to_main_sub=False)
        assert full is not None, "the full position set is a complete graph - a bijection always exists"
        return full

    def _best_assignment(
        self, players: list[Player], preferences: dict[int, RolePreference], restrict_to_main_sub: bool
    ) -> Optional[list[TeamSlot]]:
        best: Optional[list[tuple[Player, Position, float, str]]] = None
        best_cost: Optional[float] = None

        for perm in permutations(ALL_POSITIONS):
            assignment: list[tuple[Player, Position, float, str]] = []
            total_cost = 0.0
            valid = True
            for player, position in zip(players, perm):
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
