from __future__ import annotations

from app.balance.features.base import IBalanceFeature
from app.balance.features.synergy.synergy import SynergyFeature

SYNERGY_FEATURES: dict[str, type[IBalanceFeature]] = {
    "synergy": SynergyFeature,
}

__all__ = ["SynergyFeature", "SYNERGY_FEATURES"]
