from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping, Optional


class ConstraintTier(str, Enum):
    """Governs WHEN/HOW ConstraintExecutor uses a plugin's result - never
    what the plugin is "about" (see ConstraintPipeline for that, an
    independent axis).

    PARTIAL_HARD: checked mid-DFS against an incomplete roster. A plugin
    in this tier MUST be monotonic - "violated now" can never become "fine
    later" as more players are placed (e.g. Separation: once A is seated
    on team X, B being placed on team X is violated no matter who else
    still needs a seat). Enforced by ConstraintExecutor.evaluate_partial()
    only ever being handed PartialHardConstraint instances - the registry
    itself is the guardrail, not just a docstring.

    LEAF_HARD: checked only once a team is complete. Position-based rules
    (Required/Fixed Role) can ONLY live here - PositionAssigner.assign()
    requires all 5 players and produces role_source/role_penalty only at
    that point; no partial-roster code path exists.

    SOFT / PREFERENCE: never reject anything - contribute penalty/
    heuristic_score to search-branch ordering only, via
    ConstraintExecutor.compute_search_guidance()."""

    PARTIAL_HARD = "partial_hard"
    LEAF_HARD = "leaf_hard"
    SOFT = "soft"
    PREFERENCE = "preference"


class ConstraintPipeline(str, Enum):
    """Governs WHAT RESPONSIBILITY a plugin has - independent of Tier.
    A Structural check and a Role check can both be LEAF_HARD; they differ
    in what they're checking, not when they run.

    STRUCTURAL: is the team even formable (size, uniqueness, one of each
    required position).
    ROLE: Main/Sub/override/lock rules - future home for Role Learning.
    RELATIONSHIP: Duo/Trio/Separation/Rival/Synergy - future home for
    Synergy Learning. Empty this pass (no concrete plugin).
    PREFERENCE: Tournament/Clash/Admin/Server/Event/Time rules - operator/
    server policy. Empty this pass.
    SEARCH_GUIDANCE: pure heuristic-score contributors that never gate or
    penalize anything, only rank branches. Empty this pass."""

    STRUCTURAL = "structural"
    ROLE = "role"
    RELATIONSHIP = "relationship"
    PREFERENCE = "preference"
    SEARCH_GUIDANCE = "search_guidance"


class ConstraintStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"


@dataclass(frozen=True)
class ConstraintResult:
    """The one shape every Constraint plugin returns, regardless of tier
    or pipeline - tier/pipeline are data on the result, not different
    method signatures a caller has to branch on. An evaluation result,
    not a scratchpad: metadata is MappingProxyType-wrapped so nothing
    downstream (ExplainableAI, Decision Log, statistics) can mutate a
    result after a plugin returns it."""

    constraint_name: str
    pipeline: ConstraintPipeline
    tier: ConstraintTier
    status: ConstraintStatus
    reason: Optional[str] = None
    priority: int = 0
    penalty: float = 0.0
    heuristic_score: float = 0.0
    prune: bool = False
    metadata: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))
