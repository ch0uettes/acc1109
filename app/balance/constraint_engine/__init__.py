from __future__ import annotations

from app.balance.constraint_engine.aggregator import (
    DEFAULT_SEARCH_GUIDANCE_AGGREGATOR,
    SearchGuidanceAggregator,
    SearchGuidanceSummary,
)
from app.balance.constraint_engine.base import (
    IConstraint,
    LeafHardConstraint,
    PartialHardConstraint,
    PreferenceConstraint,
    SoftConstraint,
)
from app.balance.constraint_engine.context import ConstraintContext
from app.balance.constraint_engine.context_factory import (
    DEFAULT_CONSTRAINT_CONTEXT_FACTORY,
    ConstraintContextFactory,
)
from app.balance.constraint_engine.executor import ConstraintExecutor
from app.balance.constraint_engine.plugins.role import FixedRoleConstraint
from app.balance.constraint_engine.plugins.structural import (
    RequiredRoleConstraint,
    TeamSizeConstraint,
    UniquePlayerConstraint,
)
from app.balance.constraint_engine.registry import DEFAULT_CONSTRAINT_REGISTRY, ConstraintRegistry
from app.balance.constraint_engine.result import (
    ConstraintPipeline,
    ConstraintResult,
    ConstraintStatus,
    ConstraintTier,
)

# Only these 4 plugins ship active by default this pass - the other 3
# Constraint categories (Relationship/Preference/Search Guidance
# pipelines, and the Soft/Preference tiers entirely) stay empty until a
# concrete rule (Duo, Tournament, ...) actually needs them. See the
# Constraint Engine plan's "what concretely ships vs. architecture-only"
# section for why.
for _plugin_cls in (TeamSizeConstraint, UniquePlayerConstraint, RequiredRoleConstraint, FixedRoleConstraint):
    DEFAULT_CONSTRAINT_REGISTRY.register(_plugin_cls)

__all__ = [
    "ConstraintContext",
    "ConstraintContextFactory",
    "DEFAULT_CONSTRAINT_CONTEXT_FACTORY",
    "ConstraintPipeline",
    "ConstraintResult",
    "ConstraintStatus",
    "ConstraintTier",
    "IConstraint",
    "PartialHardConstraint",
    "LeafHardConstraint",
    "SoftConstraint",
    "PreferenceConstraint",
    "ConstraintRegistry",
    "DEFAULT_CONSTRAINT_REGISTRY",
    "SearchGuidanceAggregator",
    "SearchGuidanceSummary",
    "DEFAULT_SEARCH_GUIDANCE_AGGREGATOR",
    "ConstraintExecutor",
    "TeamSizeConstraint",
    "UniquePlayerConstraint",
    "RequiredRoleConstraint",
    "FixedRoleConstraint",
]
