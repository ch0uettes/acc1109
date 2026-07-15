from __future__ import annotations

from app.balance.features.base import IBalanceFeature
from app.balance.features.rating.internal_rating import InternalRatingFeature
from app.balance.features.rating.mean_balance import MeanBalanceFeature

# Rating category: Features that evaluate raw skill/rating itself. Never
# imports from lane/ or team/. Confidence is deliberately NOT a Feature
# here - it's a modifier InternalRatingFeature applies to its own
# calculation (see rating/modifiers.py), not an independent scored term.
RATING_FEATURES: dict[str, type[IBalanceFeature]] = {
    "mean_balance": MeanBalanceFeature,
    "internal_rating": InternalRatingFeature,
}

__all__ = [
    "MeanBalanceFeature",
    "InternalRatingFeature",
    "RATING_FEATURES",
]
