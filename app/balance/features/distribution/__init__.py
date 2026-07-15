from __future__ import annotations

from app.balance.features.base import IBalanceFeature
from app.balance.features.distribution.tier_distribution import TierDistributionFeature

# Distribution category: Features about how sub-groups (Riot tiers, etc.)
# are spread across teams, independent of any single aggregate rating
# number - two teams can have identical averages while one is "5 mid
# Platinums" and the other "1 Diamond carry + 4 weak Golds".
DISTRIBUTION_FEATURES: dict[str, type[IBalanceFeature]] = {
    "tier_distribution": TierDistributionFeature,
}

__all__ = [
    "TierDistributionFeature",
    "DISTRIBUTION_FEATURES",
]
