from __future__ import annotations

from dataclasses import dataclass, field

from app.models.team import Team


@dataclass
class BalanceResult:
    teams: list[Team]
    cost: float
    cost_breakdown: dict[str, float] = field(default_factory=dict)
    iterations: int = 0
