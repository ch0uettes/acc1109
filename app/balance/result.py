from __future__ import annotations

from dataclasses import dataclass, field

from app.models.team import Team


@dataclass
class FeatureContribution:
    """One Feature's full audit trail for a single BalanceResult - Raw
    Metric -> Normalized Score -> Strategy Weight -> Contribution, so a
    human (or a future debugging UI) can see exactly which Feature drove
    the final cost without re-deriving it by hand. `contribution_pct` is
    share of the *total* cost (0 when cost is 0 - nothing to attribute)."""

    name: str
    raw: float
    normalized: float
    weight: float
    contribution: float
    contribution_pct: float


@dataclass
class BalanceResult:
    teams: list[Team]
    cost: float
    cost_breakdown: dict[str, float] = field(default_factory=dict)
    contributions: list[FeatureContribution] = field(default_factory=list)
    iterations: int = 0
