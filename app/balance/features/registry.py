from __future__ import annotations

from app.balance.config import (
    DEFAULT_FEATURE_CONFIG,
    DEFAULT_NORMALIZATION_CONFIG,
    FeatureConfig,
    NormalizationConfig,
)
from app.balance.features.base import IBalanceFeature
from app.balance.features.distribution import DISTRIBUTION_FEATURES
from app.balance.features.lane import LANE_FEATURES
from app.balance.features.learning import LEARNING_FEATURES
from app.balance.features.metadata import FeatureMetadata
from app.balance.features.performance import PERFORMANCE_FEATURES
from app.balance.features.rating import RATING_FEATURES
from app.balance.features.synergy import SYNERGY_FEATURES
from app.balance.features.team import TEAM_FEATURES
from app.balance.strategy import IBalanceStrategy


class FeatureRegistry:
    """Registers every IBalanceFeature this project knows about and
    manages nothing else - not weights, not enabled/disabled state (an
    IBalanceStrategy decides that), not how scores get combined
    (BalanceEvaluator's job). Depends only on the IBalanceFeature
    interface, never on any concrete Feature's internals.

    Adding a whole new category (champion/, ai/, ...): write the category
    package with its own local *_FEATURES dict (exactly like rating/lane/
    team/performance/synergy do), register each class here (or build a
    fresh registry the same way _default_registry() does) - no existing
    Feature, category, Strategy, or BalanceEvaluator ever needs to
    change."""

    def __init__(self) -> None:
        self._features: dict[str, type[IBalanceFeature]] = {}

    def register(self, feature_cls: type[IBalanceFeature]) -> None:
        self._features[feature_cls.name] = feature_cls

    def unregister(self, name: str) -> None:
        self._features.pop(name, None)

    def get(self, name: str) -> type[IBalanceFeature]:
        return self._features[name]

    def names(self) -> list[str]:
        return list(self._features.keys())

    def by_category(self, category: str) -> list[str]:
        return [name for name, cls in self._features.items() if cls.category == category]

    def metadata(self, name: str) -> FeatureMetadata:
        return FeatureMetadata.from_feature_class(self._features[name])

    def all_metadata(self) -> list[FeatureMetadata]:
        return [self.metadata(name) for name in self._features]

    def get_active_features(
        self, strategy: IBalanceStrategy, config: NormalizationConfig = DEFAULT_NORMALIZATION_CONFIG
    ) -> list[IBalanceFeature]:
        """The Features a given Strategy actually wants to run, freshly
        instantiated (Features carry no per-run state) with `config`
        (typically a Server's saved override - see app/models/server.py)
        threaded into each Feature's own Normalizer. Strategy decides
        what's enabled; Registry only supplies the class for each name."""
        return [
            self._features[name](config)
            for name, feature_config in strategy.feature_config().items()
            if feature_config.enabled and name in self._features
        ]


def _default_registry() -> FeatureRegistry:
    registry = FeatureRegistry()
    for features_by_name in (
        RATING_FEATURES,
        LANE_FEATURES,
        DISTRIBUTION_FEATURES,
        LEARNING_FEATURES,
        TEAM_FEATURES,
        PERFORMANCE_FEATURES,
        SYNERGY_FEATURES,
    ):
        for feature_cls in features_by_name.values():
            registry.register(feature_cls)
    return registry


DEFAULT_FEATURE_REGISTRY = _default_registry()


# --- Legacy path below: app/balance/optimizer.py's RandomSwapOptimizer /
# TieredSnakeDraftOptimizer predate the Strategy-driven pipeline above and
# call `cost_fn.compute(teams)` with weights baked in ahead of time, no
# Strategy object involved. Kept working unmodified rather than touching
# optimizer.py.

FEATURE_REGISTRY: dict[str, type[IBalanceFeature]] = dict(DEFAULT_FEATURE_REGISTRY._features)


class _WeightedFeatureEvaluator:
    """Legacy shape only: weights bound at construction time, single-arg
    compute(teams). Not part of the Registry/Strategy/BalanceEvaluator
    story - see module docstring above."""

    def __init__(self, weighted_features: list[tuple[IBalanceFeature, float]]) -> None:
        self._weighted_features = weighted_features

    @property
    def features(self) -> list[IBalanceFeature]:
        return [feature for feature, _ in self._weighted_features]

    def compute(self, teams) -> tuple[float, dict[str, float]]:
        total = 0.0
        breakdown: dict[str, float] = {}
        for feature, weight in self._weighted_features:
            if weight == 0:
                continue
            value = feature.evaluate(teams)
            breakdown[feature.name] = value
            total += weight * value
        return total, breakdown

    evaluate = compute


def build_balance_evaluator(
    config: dict[str, FeatureConfig] = DEFAULT_FEATURE_CONFIG,
    registry: dict[str, type[IBalanceFeature]] = FEATURE_REGISTRY,
) -> _WeightedFeatureEvaluator:
    weighted = [
        (registry[name](), feature_config.weight)
        for name, feature_config in config.items()
        if feature_config.enabled
    ]
    return _WeightedFeatureEvaluator(weighted)


def default_balance_evaluator(
    config: dict[str, FeatureConfig] = DEFAULT_FEATURE_CONFIG,
) -> _WeightedFeatureEvaluator:
    return build_balance_evaluator(config)
