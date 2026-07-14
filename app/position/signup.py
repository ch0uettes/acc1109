from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

from app.models.player import Player
from app.position.schemas import RolePreference


class PlayerSignup(BaseModel):
    """One player's participation in one team-generation run - the actual
    input to TeamBalancer.generate_teams(), replacing a raw list[Player].
    `match_override`, when set, is this-match-only and never written back
    to the Player's Profile."""

    player: Player
    match_override: Optional[RolePreference] = None
