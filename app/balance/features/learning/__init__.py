from __future__ import annotations

from app.balance.features.base import IBalanceFeature
from app.balance.features.learning.internal_rating import InternalRatingFeature

# Learning category: Features built on data this community's own games
# produced (Internal Rating, earned via
# rating.updater.ExpectedPerformanceUpdateStrategy) rather than an
# external/official source - the natural home for future AI-learned
# signals (synergy learning, MVP-based learning, etc. planned for v2.0).
# Confidence is deliberately NOT its own Feature here - it's a modifier
# InternalRatingFeature applies to itself (see learning/modifiers.py).
LEARNING_FEATURES: dict[str, type[IBalanceFeature]] = {
    "internal_rating": InternalRatingFeature,
}

__all__ = [
    "InternalRatingFeature",
    "LEARNING_FEATURES",
]
