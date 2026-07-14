from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum

from app.models.team import Team


class FeaturePriority(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class IBalanceFeature(ABC):
    """One independent term of the balance objective function. A Feature
    computes its own raw score from `teams` AND owns the Normalizer that
    turns that raw score into a comparable [0, 1] value - it never knows
    about any other Feature, never carries a weight of its own, and never
    knows whether it's even enabled. Normalization lives here (not in
    BalanceEvaluator) because each Feature's raw value has its own
    natural scale and shape - team_variance is a squared-rating-point
    unit with a huge dynamic range (fits a Logarithmic Normalizer),
    average_rating is a single linear rating-point gap where a smooth
    cutoff matters (fits a Logistic Normalizer), tier_distribution is a
    small hand-tuned integer gap (fits a Piecewise Normalizer) - a single
    generic normalization scheme can't fit all of these. The plugin
    contract: implement `evaluate_raw()` + `normalize()`, declare the
    metadata below, register it - nothing else in the system changes.

    Enabled/weight are decided entirely by an IBalanceStrategy at
    evaluation time (see app/balance/strategy.py) - `default_enabled`/
    `default_weight` here are just this Feature's own opinion of a
    sensible fallback, used by FeatureRegistry when no Strategy overrides
    it, not a value the Feature applies itself.

    Lives at the package root (not inside any category) because it's the
    shared contract every category depends on - categories depend on
    this, never on each other."""

    name: str
    category: str
    description: str
    default_enabled: bool = True
    default_weight: float = 1.0
    priority: FeaturePriority = FeaturePriority.MEDIUM

    @abstractmethod
    def evaluate_raw(self, teams: list[Team]) -> float:
        """This Feature's raw, unnormalized metric in its own natural
        unit - never compared directly against another Feature's raw
        value (see normalize())."""
        ...

    @abstractmethod
    def normalize(self, raw: float) -> float:
        """raw -> [0, 1] via this Feature's own Normalizer (see
        app/balance/features/scaling.py), so BalanceEvaluator can combine
        it with every other Feature's normalized score using only a
        Strategy's weight - no Feature's raw unit scale leaks through."""
        ...

    def evaluate(self, teams: list[Team]) -> float:
        """Convenience one-shot: normalize(evaluate_raw(teams)). Prefer
        calling evaluate_raw()/normalize() separately when the raw value
        is also needed for display (see BalanceEvaluator)."""
        return self.normalize(self.evaluate_raw(teams))
