from __future__ import annotations

from app.balance.features.base import FeaturePriority, IBalanceFeature
from app.balance.features.evaluator import BalanceEvaluator
from app.balance.features.lane import LaneBalanceFeature, RolePenaltyFeature
from app.balance.features.metadata import FeatureMetadata
from app.balance.features.performance import RecentFormFeature
from app.balance.features.rating import InternalRatingFeature, MeanBalanceFeature
from app.balance.features.registry import (
    DEFAULT_FEATURE_REGISTRY,
    FEATURE_REGISTRY,
    FeatureRegistry,
    build_balance_evaluator,
    default_balance_evaluator,
)
from app.balance.features.synergy import SynergyFeature
from app.balance.features.team import (
    OutlierPenaltyFeature,
    PenaltyFeature,
    TeamVarianceFeature,
    TierDistributionFeature,
)

# Re-exports every public name from this package's internals, so
# `from app.balance.features import X` keeps working unchanged everywhere
# in the codebase regardless of which submodule X actually lives in.
__all__ = [
    "IBalanceFeature",
    "FeaturePriority",
    "FeatureMetadata",
    "FeatureRegistry",
    "DEFAULT_FEATURE_REGISTRY",
    "BalanceEvaluator",
    "FEATURE_REGISTRY",
    "build_balance_evaluator",
    "default_balance_evaluator",
    "MeanBalanceFeature",
    "InternalRatingFeature",
    "OutlierPenaltyFeature",
    "LaneBalanceFeature",
    "RolePenaltyFeature",
    "TeamVarianceFeature",
    "TierDistributionFeature",
    "PenaltyFeature",
    "RecentFormFeature",
    "SynergyFeature",
]
