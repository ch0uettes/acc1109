from __future__ import annotations

from app.models.player import Player
from app.position.preference_manager import RolePreferenceManager
from app.position.schemas import RolePreference
from app.utils.enums import Position, Tier


def _player(main_role: Position, sub_role: Position | None = None) -> Player:
    return Player(nickname="p", tier=Tier.GOLD, main_role=main_role, sub_role=sub_role)


def test_profile_wins_when_no_override():
    player = _player(Position.MID, Position.TOP)
    resolved = RolePreferenceManager().resolve(player)
    assert resolved == RolePreference(main=Position.MID, sub=Position.TOP)


def test_match_override_wins_over_profile():
    player = _player(Position.MID, Position.TOP)
    override = RolePreference(main=Position.JUNGLE, sub=Position.SUPPORT)
    resolved = RolePreferenceManager().resolve(player, match_override=override)
    assert resolved == override
