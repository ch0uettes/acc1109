from __future__ import annotations

import statistics
from typing import Literal, Optional

from pydantic import BaseModel

from app.models.player import Player
from app.utils.enums import Position


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
