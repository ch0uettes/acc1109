from __future__ import annotations

from app.balance.features.base import IBalanceFeature
from app.balance.features.lane.lane_balance import LaneBalanceFeature
from app.balance.features.lane.role_penalty import RolePenaltyFeature

# Lane category: Features about lane matchups and position assignment.
# Never imports from rating/ or team/.
LANE_FEATURES: dict[str, type[IBalanceFeature]] = {
    "lane_balance": LaneBalanceFeature,
    "role_penalty": RolePenaltyFeature,
}

__all__ = ["LaneBalanceFeature", "RolePenaltyFeature", "LANE_FEATURES"]
