from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

from app.models.player import Player
from app.position.schemas import RolePreference


class PlayerSignup(BaseModel):
    """One player's participation in one team-generation run - the actual
    input to TeamBalancer.generate_teams(), replacing a raw list[Player].
    `match_override`, when set, is this-match-only and never written back
    to the Player's Profile.

    `enforce_fixed_role` decides how strongly `match_override` is honored -
    True (default) makes it a hard requirement enforced by
    FixedRoleConstraint (see app/balance/constraint_engine/plugins/role.py):
    every returned candidate must actually place this player at the
    overridden position. False keeps `match_override` as this player's
    this-match main/sub preference for RolePreferenceManager/scoring
    purposes only - a soft nudge the search can trade off against, exactly
    like a normal profile preference, never hard-enforced. Irrelevant when
    `match_override` is None."""

    player: Player
    match_override: Optional[RolePreference] = None
    enforce_fixed_role: bool = True
