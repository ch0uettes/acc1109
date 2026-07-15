from __future__ import annotations

from typing import Optional

from app.balance.constraint_engine.base import IConstraint
from app.balance.constraint_engine.result import ConstraintPipeline, ConstraintTier


class ConstraintRegistry:
    """Same philosophy as FeatureRegistry: register/unregister a plugin
    class, resolve the active set for a given tier (optionally filtered
    by pipeline) freshly instantiated, sorted by priority descending.
    SearchEngine never touches this directly - only ConstraintExecutor
    does, resolved once per search_top_k() call (see executor.py), not
    per DFS node."""

    def __init__(self) -> None:
        self._constraints: dict[str, type[IConstraint]] = {}

    def register(self, constraint_cls: type[IConstraint]) -> None:
        self._constraints[constraint_cls.name] = constraint_cls

    def unregister(self, name: str) -> None:
        self._constraints.pop(name, None)

    def get(self, name: str) -> type[IConstraint]:
        return self._constraints[name]

    def names(self) -> list[str]:
        return list(self._constraints.keys())

    def active(
        self,
        tier: ConstraintTier,
        pipeline: Optional[ConstraintPipeline] = None,
        priority_overrides: Optional[dict[str, int]] = None,
    ) -> list[IConstraint]:
        """Every registered plugin of `tier` (optionally further filtered
        to one `pipeline`), freshly instantiated, sorted by effective
        priority descending - `priority_overrides.get(name, default)`.
        Priority resolution beyond this (Strategy overrides Server
        overrides plugin default) is ConstraintExecutor's job: it passes
        in the already-resolved override dict, this method just sorts by
        whatever it's given."""
        overrides = priority_overrides or {}
        matches = [
            cls
            for cls in self._constraints.values()
            if cls.tier == tier and (pipeline is None or cls.pipeline == pipeline)
        ]
        matches.sort(key=lambda cls: overrides.get(cls.name, cls.default_priority), reverse=True)
        return [cls() for cls in matches]


DEFAULT_CONSTRAINT_REGISTRY = ConstraintRegistry()
