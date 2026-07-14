from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class OCRPlayerRow(BaseModel):
    """One parsed row from a result-screen screenshot. Every field is a
    best-effort OCR read and is meant to be shown to the user for
    confirmation/correction before it's used for anything - OCR misreads
    names, digits, and especially thousand-separators often enough that
    committing it unreviewed would be irresponsible."""

    raw_name: str
    matched_player_id: Optional[int] = None
    champion: str = ""
    team_index: int = 0
    kills: int = 0
    deaths: int = 0
    assists: int = 0
    cs: int = 0
    gold: int = 0
    damage: int = 0
    vision_score: int = 0


class MatchResultData(BaseModel):
    """Structured output of the OCR pipeline."""

    participants: list[OCRPlayerRow]
    winning_team_index: Optional[int]
    raw_text: str
