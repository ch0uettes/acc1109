from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.utils.enums import Division, Position, Tier


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


class PlayerSnapshot(BaseModel):
    """Frozen copy of the Player fields relevant to reproducing a
    decision - not a live reference. A Player's profile can change after
    this decision was logged (rating updates, role edits, ...); this
    snapshot is what the AI actually saw at execution time, so a future
    Learning Engine trains against the real input, not today's edited
    state."""

    id: int
    nickname: str
    tier: Tier
    division: Division
    main_role: Position
    sub_role: Optional[Position] = None
    final_rating: float
    internal_rating: float
    confidence: float


class SearchStatisticsSnapshot(BaseModel):
    """Plain-dict-friendly copy of app.balance.execution_context.SearchStatistics."""

    nodes_expanded: int
    elapsed_seconds: float
    candidate_count: int
    node_budget_hit: bool
    time_budget_hit: bool


class VersionMetadataSnapshot(BaseModel):
    """Plain-dict-friendly copy of app.balance.execution_context.VersionMetadata."""

    app_version: str
    strategy_name: str
    search_policy_name: str
    feature_weights: dict[str, float]


class DecisionLogEntry(BaseModel):
    """One team-generation decision: what the AI recommended, and what
    the operator actually chose. `chosen_rank` != 1 is the Human
    Feedback signal v2.0's AI Learning Engine will train against - the
    AI ranked something else first, but a human judged this one better.

    execution_id/player_snapshot/search_statistics/version_metadata/
    execution_time_seconds/candidate_count/search_policy_name are all
    Optional/empty-default because rows written before this schema
    expansion have NULL in these DB columns - see
    DecisionLogRepository._to_domain()."""

    id: Optional[int] = None
    server_id: int
    execution_id: Optional[str] = None
    created_at: datetime
    strategy_name: str
    search_policy_name: Optional[str] = None
    player_ids: list[int]
    player_snapshot: list[PlayerSnapshot] = []
    search_statistics: Optional[SearchStatisticsSnapshot] = None
    version_metadata: Optional[VersionMetadataSnapshot] = None
    execution_time_seconds: Optional[float] = None
    candidate_count: Optional[int] = None
    recommendations: list[RecommendationSnapshot]
    chosen_rank: int
    chosen_at: datetime
    reason: Optional[str] = None
