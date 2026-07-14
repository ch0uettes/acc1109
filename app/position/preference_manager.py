from __future__ import annotations

from typing import Optional

from app.models.player import Player
from app.position.schemas import RolePreference


class RolePreferenceManager:
    """Resolves the priority order: this-match override -> Player Profile.
    Only 2 branches in practice - Riot's recommendation (tier 3) is never
    a live fallback here, because it was already folded into the Profile
    once, permanently, at registration time (see PlayerService.
    register_player, which seeds main_role/sub_role from the
    RoleRecommendation while separately keeping the raw recommendation in
    Player.recommended_main_role/recommended_sub_role as reference-only
    metadata). Writing a 3rd branch that re-reads the Riot recommendation
    here would be dead code that never fires, since main_role is always
    set by the time a player can be signed up for a match."""

    def resolve(self, player: Player, match_override: Optional[RolePreference] = None) -> RolePreference:
        if match_override is not None:
            return match_override
        return RolePreference(main=player.main_role, sub=player.sub_role)
