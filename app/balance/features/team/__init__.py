from __future__ import annotations

from app.balance.features.base import IBalanceFeature
from app.balance.features.team.inter_team_balance import InterTeamBalanceFeature
from app.balance.features.team.penalty import PenaltyFeature
from app.balance.features.team.team_variance import TeamVarianceFeature
from app.balance.features.team.tier_distribution import TierDistributionFeature

# Team category: Features about overall team-composition balance. Never
# imports from rating/ or lane/.
TEAM_FEATURES: dict[str, type[IBalanceFeature]] = {
    "inter_team_balance": InterTeamBalanceFeature,
    "team_variance": TeamVarianceFeature,
    "tier_distribution": TierDistributionFeature,
    "penalty": PenaltyFeature,
}

__all__ = [
    "InterTeamBalanceFeature",
    "TeamVarianceFeature",
    "TierDistributionFeature",
    "PenaltyFeature",
    "TEAM_FEATURES",
]
