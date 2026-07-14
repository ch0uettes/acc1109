from __future__ import annotations

from app.balance.config import DEFAULT_NORMALIZATION_CONFIG, NormalizationConfig
from app.balance.features.base import FeaturePriority, IBalanceFeature
from app.models.team import Team


class RecentFormFeature(IBalanceFeature):
    """First occupant of the performance/ category - future siblings
    (MVPFeature, CarryPotentialFeature, VolatilityFeature, ...) join here
    without touching rating/lane/team."""

    name = "recent_form"
    category = "performance"
    description = "최근 내전 성적(승/패 흐름) 반영 - 미구현"
    default_enabled = False
    default_weight = 0.0
    priority = FeaturePriority.LOW

    def __init__(self, config: NormalizationConfig = DEFAULT_NORMALIZATION_CONFIG) -> None:
        pass  # unused until this Feature is actually implemented

    def evaluate_raw(self, teams: list[Team]) -> float:
        raise NotImplementedError("Planned: factor in recent win/loss trend")

    def normalize(self, raw: float) -> float:
        raise NotImplementedError("Planned: factor in recent win/loss trend")
