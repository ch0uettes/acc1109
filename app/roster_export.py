from __future__ import annotations

import io

import pandas as pd

from app.models.player import Player
from app.models.team import SavedTeam
from app.rating.official import master_stage_from
from app.utils.enums import Tier

UNKNOWN_PLAYER_LABEL = "알 수 없음"


def tier_label(player: Player | None) -> str:
    """Same shape as player_page.py's _tier_display(), but takes a whole
    Player (or None, for a saved slot whose player row somehow can't be
    found) rather than three separate optional fields - this module never
    has a bare tier/division/lp without a Player attached."""
    if player is None:
        return UNKNOWN_PLAYER_LABEL
    if player.tier == Tier.MASTER:
        return f"마스터 {master_stage_from(player.tier, player.lp)}"
    return f"{player.tier.value} {player.division.value}"


def saved_teams_to_txt(saved_teams: list[SavedTeam]) -> str:
    """Plain-text roster, one block per team - meant to be pasted directly
    into Discord/a chat, not parsed back by this app (see app.roster_import
    for the reverse direction, which expects a nickname+Riot ID shape,
    not this team-roster shape)."""
    blocks = []
    for team in saved_teams:
        lines = [f"{team.index + 1}팀"]
        for entry in team.entries:
            name = entry.player.nickname if entry.player else UNKNOWN_PLAYER_LABEL
            lines.append(f"{entry.position.value}: {name} ({tier_label(entry.player)})")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks) + "\n"


def saved_teams_to_xlsx_bytes(saved_teams: list[SavedTeam]) -> bytes:
    """One row per player (팀/포지션/닉네임/티어) - a flat table rather than
    the TXT export's per-team blocks, since that's the shape a spreadsheet
    is actually useful for (sort/filter by team or position)."""
    rows = [
        {
            "팀": team.index + 1,
            "포지션": entry.position.value,
            "닉네임": entry.player.nickname if entry.player else UNKNOWN_PLAYER_LABEL,
            "티어": tier_label(entry.player),
        }
        for team in saved_teams
        for entry in team.entries
    ]
    buffer = io.BytesIO()
    pd.DataFrame(rows).to_excel(buffer, index=False, engine="openpyxl")
    return buffer.getvalue()
