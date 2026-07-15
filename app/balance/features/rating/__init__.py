from __future__ import annotations

from app.balance.features.base import IBalanceFeature
from app.balance.features.rating.mean_balance import MeanBalanceFeature
from app.balance.features.rating.outlier_penalty import OutlierPenaltyFeature
from app.balance.features.rating.team_variance import TeamVarianceFeature

# Rating category: every Feature whose job is to judge Rating balance
# itself (전체 평균 균형/극단 팀 탐지/팀 내부 안정성) - never imports from
# lane/distribution/learning. These three are deliberately kept together
# despite different formulas (stddev-of-means / max-abs-deviation /
# mean-of-per-team-variance) because they share one responsibility: is
# the Rating spread across and within teams fair. See each Feature's own
# docstring for why its specific formula can't substitute for the others.
RATING_FEATURES: dict[str, type[IBalanceFeature]] = {
    "mean_balance": MeanBalanceFeature,
    "outlier_penalty": OutlierPenaltyFeature,
    "team_variance": TeamVarianceFeature,
}

__all__ = [
    "MeanBalanceFeature",
    "OutlierPenaltyFeature",
    "TeamVarianceFeature",
    "RATING_FEATURES",
]
