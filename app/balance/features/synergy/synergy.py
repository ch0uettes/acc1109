from __future__ import annotations

from app.balance.config import DEFAULT_NORMALIZATION_CONFIG, NormalizationConfig
from app.balance.features.base import FeaturePriority, IBalanceFeature
from app.models.team import Team


class SynergyFeature(IBalanceFeature):
    """First occupant of the synergy/ category - future siblings
    (DuoSynergyFeature, TeamExperienceFeature, PlayStyleFeature, ...)
    join here without touching rating/lane/team/performance."""

    name = "synergy"
    category = "synergy"
    description = "듀오/팀 시너지 반영 - 미구현"
    default_enabled = False
    default_weight = 0.0
    priority = FeaturePriority.LOW

    def __init__(self, config: NormalizationConfig = DEFAULT_NORMALIZATION_CONFIG) -> None:
        pass  # unused until this Feature is actually implemented

    def evaluate_raw(self, teams: list[Team]) -> float:
        raise NotImplementedError("Planned: reward/penalize known duo synergy")

    def normalize(self, raw: float) -> float:
        raise NotImplementedError("Planned: reward/penalize known duo synergy")
