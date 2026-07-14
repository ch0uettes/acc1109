from __future__ import annotations

from pydantic import BaseModel

from app.utils.enums import Division, Position, Tier


class RiotAccount(BaseModel):
    """Account-V1 response: the account tied to a Riot ID (gameName#tagLine)."""

    puuid: str
    game_name: str
    tag_line: str


class RankInfo(BaseModel):
    tier: Tier
    division: Division
    lp: int
    wins: int
    losses: int


class MatchHistoryEntry(BaseModel):
    match_id: str
    champion: str
    position: Position
    win: bool


class ChampionMasteryEntry(BaseModel):
    champion: str
    mastery_points: int
