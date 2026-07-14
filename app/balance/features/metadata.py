from __future__ import annotations

from dataclasses import dataclass

from app.balance.features.base import FeaturePriority, IBalanceFeature


@dataclass(frozen=True)
class FeatureMetadata:
    """Everything about a Feature that isn't the calculation itself -
    what FeatureRegistry hands back for introspection/UI display (a
    settings screen listing every known Feature, its category, and its
    suggested default). Derived straight from the Feature class's own
    declared attributes, never duplicated by hand."""

    name: str
    category: str
    description: str
    default_enabled: bool
    default_weight: float
    priority: FeaturePriority

    @classmethod
    def from_feature_class(cls, feature_cls: type[IBalanceFeature]) -> "FeatureMetadata":
        return cls(
            name=feature_cls.name,
            category=feature_cls.category,
            description=feature_cls.description,
            default_enabled=feature_cls.default_enabled,
            default_weight=feature_cls.default_weight,
            priority=feature_cls.priority,
        )
