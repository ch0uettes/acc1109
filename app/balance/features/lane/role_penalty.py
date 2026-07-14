from __future__ import annotations

from app.balance.config import DEFAULT_NORMALIZATION_CONFIG, NormalizationConfig
from app.balance.features.base import FeaturePriority, IBalanceFeature
from app.balance.features.scaling import LinearNormalizer
from app.models.team import Team


class RolePenaltyFeature(IBalanceFeature):
    """Sums Role Penalty (main=0/sub=10/other=100 by default - see
    RolePenaltyConfig) across every assigned slot. The hard constraint
    itself ("never use Other if a full Main/Sub team exists") lives in
    PositionAssigner, which structurally excludes Other from the
    candidate set whenever avoidable; this feature is what still prefers
    Main over Sub when both are available, and prices in Other whenever
    it's genuinely unavoidable. Requires Team.slots - only the
    position-aware pipeline (TeamBalancer + TeamSearchEngine +
    PositionAssigner) populates it.

    Normalized linearly (raw / role_penalty_max, clipped to 1.0) - the
    raw unit is already a deliberately-chosen point scale (see
    RolePenaltyConfig), so it doesn't need a curve, just a ceiling."""

    name = "role_penalty"
    category = "lane"
    description = "Main/Sub/Other Role 배정 페널티 계산"
    default_enabled = True
    default_weight = 0.10
    priority = FeaturePriority.MEDIUM

    def __init__(self, config: NormalizationConfig = DEFAULT_NORMALIZATION_CONFIG) -> None:
        self._normalizer = LinearNormalizer(config.role_penalty_max)

    def evaluate_raw(self, teams: list[Team]) -> float:
        if any(team.slots is None for team in teams):
            raise ValueError("RolePenaltyFeature requires Team.slots (position-aware pipeline only)")
        return sum(slot.role_penalty for team in teams for slot in team.slots)

    def normalize(self, raw: float) -> float:
        return self._normalizer(raw)
