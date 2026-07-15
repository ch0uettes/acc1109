from __future__ import annotations

from abc import ABC, abstractmethod

from app.balance.constraint_engine.context import ConstraintContext
from app.balance.constraint_engine.result import ConstraintPipeline, ConstraintResult, ConstraintTier


class IConstraint(ABC):
    """One independent Constraint plugin. Mirrors IBalanceFeature's
    contract exactly (name/category-equivalent attributes, one eval
    method, registered once, never aware of other plugins or of
    ConstraintExecutor's orchestration). `tier` and `pipeline` are class
    attributes read into every ConstraintResult this plugin returns -
    tier governs WHEN/HOW ConstraintExecutor uses the result, pipeline
    governs WHAT RESPONSIBILITY the plugin has; see result.py for both
    enums' full docstrings.

    Every subclass implements exactly one method, `evaluate(context) ->
    ConstraintResult` - the same shape regardless of tier. Type-level
    safety for the PARTIAL_HARD monotonicity requirement comes from which
    of the four base classes below a plugin subclasses, not from the
    result shape - ConstraintExecutor.evaluate_partial() only ever
    resolves PartialHardConstraint instances from the registry, so a
    LeafHardConstraint/SoftConstraint/PreferenceConstraint can never be
    accidentally wired into the pruning path."""

    name: str
    pipeline: ConstraintPipeline
    tier: ConstraintTier
    default_priority: int
    description: str

    @abstractmethod
    def evaluate(self, context: ConstraintContext) -> ConstraintResult:
        ...


class PartialHardConstraint(IConstraint):
    """Checked mid-DFS against an incomplete roster (context.rosters/
    .team_index/.candidate_player populated, context.teams is None).
    MUST be monotonic: once evaluate() returns prune=True for a given
    partial state, every possible completion of that state must also be
    invalid - never "maybe fine once more players are placed." A
    plugin that can't guarantee this belongs in LeafHardConstraint
    instead, checked only once the team is complete."""

    tier = ConstraintTier.PARTIAL_HARD


class LeafHardConstraint(IConstraint):
    """Checked only once a team is complete (context.teams populated,
    context.rosters/.team_index/.candidate_player are None/not
    meaningful). The only tier that can reference role_source/
    role_penalty/position assignment - PositionAssigner.assign() requires
    a full 5-player roster, so nothing about position is knowable on a
    partial state."""

    tier = ConstraintTier.LEAF_HARD


class SoftConstraint(IConstraint):
    """Never rejects a candidate - contributes `penalty`/`heuristic_score`
    to ConstraintExecutor.compute_search_guidance()'s branch ordering
    only. Evaluated against partial state, same context shape as
    PartialHardConstraint but never sets prune=True."""

    tier = ConstraintTier.SOFT


class PreferenceConstraint(IConstraint):
    """Same shape and evaluation point as SoftConstraint - operator/
    server policy rules (Tournament/Clash/Admin/Server/Event/Time), lowest
    priority tier. Kept as a distinct class (not just a SoftConstraint
    subclass) so ConstraintRegistry/ConstraintExecutor can filter and
    report on it separately from rating-adjacent Soft constraints."""

    tier = ConstraintTier.PREFERENCE
