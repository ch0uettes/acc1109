from __future__ import annotations

import statistics
from typing import Literal, Optional

from pydantic import BaseModel

from app.models.player import Player
from app.utils.enums import Division, Position, Tier


class TeamSlot(BaseModel):
    """One player's *assigned* lane within a team, as decided by
    PositionAssigner - independent of, and possibly different from, the
    player's Profile main_role (e.g. when Sub or Other had to be used)."""

    position: Position
    player: Player
    role_penalty: float
    role_source: Literal["main", "sub", "other"]


class Team(BaseModel):
    """One side of a generated match. `index` generalizes beyond 2 teams
    so the balancer can split 5N participants into N teams of 5.

    `slots` is populated only by the position-aware pipeline (TeamBalancer
    + TeamSearchEngine + PositionAssigner); legacy TeamOptimizer strategies
    (RandomSwapOptimizer, TieredSnakeDraftOptimizer) never set it, so
    `position_for()` transparently falls back to `player.main_role`."""

    index: int
    players: list[Player]
    slots: Optional[list[TeamSlot]] = None

    @property
    def average_rating(self) -> float:
        return statistics.fmean(p.final_rating for p in self.players)

    @property
    def total_rating(self) -> float:
        return sum(p.final_rating for p in self.players)

    def position_for(self, player_id: int) -> Position:
        if self.slots is not None:
            return next(s.position for s in self.slots if s.player.id == player_id)
        return next(p for p in self.players if p.id == player_id).main_role


class SavedRosterEntry(BaseModel):
    """One player's position within a previously-saved (persisted) team -
    reloaded from the `teams`/`team_players` tables, not a fresh balancer
    result. Deliberately NOT a TeamSlot: role_penalty/role_source are
    scoring-time artifacts that were never persisted alongside the saved
    roster, so reconstructing them here would just be guessing."""

    position: Position
    player: Optional[Player]


class SavedTeam(BaseModel):
    """One team from a previously-saved balancer run, as reloaded via
    TeamService.load_saved_run() - see SavedRosterEntry for why this isn't
    just a plain Team/TeamSlot."""

    index: int
    entries: list[SavedRosterEntry]
    # The team's highest-tier player (see captain_of) - shown as 팀장.
    captain_player_id: Optional[int] = None


_TIER_ORDER = [Tier.IRON, Tier.BRONZE, Tier.SILVER, Tier.GOLD, Tier.PLATINUM, Tier.EMERALD, Tier.DIAMOND, Tier.MASTER]
_DIVISION_ORDER = [Division.IV, Division.III, Division.II, Division.I]


def tier_strength(player: Player) -> tuple[int, int, int, float]:
    """Sort key for "who has the highest tier": tier, then division (I is
    best), then LP (Master has no division, so LP alone decides there).
    UNRANKED ranks below Iron; ties - including between unranked players,
    who all share the same key otherwise - fall back to base_rating
    (official or seed)."""
    if player.tier not in _TIER_ORDER:
        return (-1, 0, 0, player.base_rating)
    return (_TIER_ORDER.index(player.tier), _DIVISION_ORDER.index(player.division), player.lp, player.base_rating)


def captain_of(players: list[Player]) -> Optional[Player]:
    return max(players, key=tier_strength, default=None)
