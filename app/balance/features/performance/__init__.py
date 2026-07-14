from __future__ import annotations

from app.balance.features.base import IBalanceFeature
from app.balance.features.performance.recent_form import RecentFormFeature

PERFORMANCE_FEATURES: dict[str, type[IBalanceFeature]] = {
    "recent_form": RecentFormFeature,
}

__all__ = ["RecentFormFeature", "PERFORMANCE_FEATURES"]
