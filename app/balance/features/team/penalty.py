from __future__ import annotations

from app.balance.config import DEFAULT_NORMALIZATION_CONFIG, NormalizationConfig
from app.balance.features.base import FeaturePriority, IBalanceFeature
from app.models.team import Team


class PenaltyFeature(IBalanceFeature):
    """Provisional home for team-composition hard constraints (e.g. keep
    two specific players together/apart) - doesn't fit rating/lane
    cleanly, so it lives alongside team-composition concerns until it has
    a real implementation and its own category, if warranted."""

    name = "penalty"
    category = "team"
    description = "팀 구성 하드 제약 조건 (예: 특정 인원 묶기/분리) - 미구현"
    default_enabled = False
    default_weight = 0.0
    priority = FeaturePriority.LOW

    def __init__(self, config: NormalizationConfig = DEFAULT_NORMALIZATION_CONFIG) -> None:
        pass  # unused until this Feature is actually implemented

    def evaluate_raw(self, teams: list[Team]) -> float:
        raise NotImplementedError("Planned: hard constraints, e.g. keep/split specific players")

    def normalize(self, raw: float) -> float:
        raise NotImplementedError("Planned: hard constraints, e.g. keep/split specific players")
