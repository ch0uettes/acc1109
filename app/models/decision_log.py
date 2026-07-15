from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class FeatureContributionSnapshot(BaseModel):
    """Plain-dict-friendly copy of app.balance.result.FeatureContribution,
    frozen at decision time - the log must stay readable even if a
    Feature is later renamed/removed/reweighted, so it doesn't reference
    live Feature classes at all, just names and numbers."""

    name: str
    raw: float
    normalized: float
    weight: float
    contribution: float
    contribution_pct: float


class RecommendationSnapshot(BaseModel):
    """One of the combos the AI offered, frozen at decision time."""

    rank: int
    cost: float
    team_player_ids: list[list[int]]
    contributions: list[FeatureContributionSnapshot]


class DecisionLogEntry(BaseModel):
    """One team-generation decision: what the AI recommended, and what
    the operator actually chose. `chosen_rank` != 1 is the Human
    Feedback signal v2.0's AI Learning Engine will train against - the
    AI ranked something else first, but a human judged this one better."""

    id: Optional[int] = None
    server_id: int
    created_at: datetime
    strategy_name: str
    player_ids: list[int]
    recommendations: list[RecommendationSnapshot]
    chosen_rank: int
    chosen_at: datetime
    reason: Optional[str] = None
