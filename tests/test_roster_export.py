from __future__ import annotations

import io

import pandas as pd
import pytest

from app.models.player import Player
from app.models.team import SavedRosterEntry, SavedTeam
from app.roster_export import UNKNOWN_PLAYER_LABEL, saved_teams_to_txt, saved_teams_to_xlsx_bytes
from app.utils.enums import Division, Position, Tier


def _player(nickname: str, tier: Tier = Tier.GOLD, division: Division = Division.II, lp: int = 40) -> Player:
    return Player(nickname=nickname, tier=tier, division=division, lp=lp, main_role=Position.MID)


@pytest.fixture
def two_saved_teams() -> list[SavedTeam]:
    top, jungle = _player("탑러버"), _player("정글러", tier=Tier.MASTER, lp=250)
    mid, adc = _player("미드왕"), _player("원딜황")
    return [
        SavedTeam(
            index=0,
            entries=[
                SavedRosterEntry(position=Position.TOP, player=top),
                SavedRosterEntry(position=Position.JUNGLE, player=jungle),
            ],
        ),
        SavedTeam(
            index=1,
            entries=[
                SavedRosterEntry(position=Position.MID, player=mid),
                SavedRosterEntry(position=Position.ADC, player=adc),
                SavedRosterEntry(position=Position.SUPPORT, player=None),
            ],
        ),
    ]


def test_txt_export_has_one_block_per_team_with_position_and_nickname(two_saved_teams):
    text = saved_teams_to_txt(two_saved_teams)
    assert "1팀" in text
    assert "2팀" in text
    assert "TOP: 탑러버 (GOLD II)" in text
    assert "JUNGLE: 정글러 (마스터 1)" in text


def test_txt_export_shows_unknown_for_a_missing_player(two_saved_teams):
    text = saved_teams_to_txt(two_saved_teams)
    assert f"SUPPORT: {UNKNOWN_PLAYER_LABEL}" in text


def test_xlsx_export_produces_one_row_per_player(two_saved_teams):
    data = saved_teams_to_xlsx_bytes(two_saved_teams)
    df = pd.read_excel(io.BytesIO(data))

    assert len(df) == sum(len(t.entries) for t in two_saved_teams)
    assert list(df.columns) == ["팀", "포지션", "닉네임", "티어"]
    top_row = df[df["닉네임"] == "탑러버"].iloc[0]
    assert top_row["팀"] == 1
    assert top_row["포지션"] == "TOP"
    assert top_row["티어"] == "GOLD II"


def test_xlsx_export_shows_unknown_for_a_missing_player(two_saved_teams):
    data = saved_teams_to_xlsx_bytes(two_saved_teams)
    df = pd.read_excel(io.BytesIO(data))
    support_row = df[df["포지션"] == "SUPPORT"].iloc[0]
    assert support_row["닉네임"] == UNKNOWN_PLAYER_LABEL
