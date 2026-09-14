from __future__ import annotations

from app.balance.config import DEFAULT_HARD_CONSTRAINT_CONFIG, HardConstraintConfig
from app.models.team import Team
from app.utils.enums import Position

TEAM_SIZE = 5


class HardConstraintLayer:
    """Feasibility Check step, run before any Cost is computed. Two
    tiers, both gated behind this one layer:

    1. Structural feasibility - always on, never configurable: every
       team must have exactly TEAM_SIZE players, and (when Team.slots is
       populated) exactly one of each Position. In this codebase
       PositionAssigner already guarantees this for every candidate it
       produces (Other is a structural fallback that always yields a
       valid bijection - see app/position/assigner.py), so this check
       exists as a defensive invariant / extension point, not because it
       currently rejects anything.

    2. Explicit numeric thresholds from HardConstraintConfig - OFF by
       default (every field is None). Aggressive numeric Hard
       Constraints create cliff-edge behavior (a rating gap of 801 is
       rejected while 799 passes for no principled reason), which this
       project deliberately avoids: the default fairness lever is Soft
       Penalty (BalanceEvaluator's normalized + weighted Features), not
       rejection. An operator can still tighten a field on
       HardConstraintConfig to hard-exclude certain splits for one
       server/event, but that's an opt-in, not the default behavior."""

    def __init__(self, config: HardConstraintConfig = DEFAULT_HARD_CONSTRAINT_CONFIG) -> None:
        self.config = config

    def is_feasible(self, teams: list[Team], raw_breakdown: dict[str, float]) -> bool:
        if not self._is_structurally_valid(teams):
            return False

        cfg = self.config
        if cfg.mean_balance_diff_max is not None:
            if self._raw(raw_breakdown, "mean_balance", cfg) > cfg.mean_balance_diff_max:
                return False
        if cfg.lane_diff_max is not None:
            if self._raw(raw_breakdown, "lane_balance", cfg) > cfg.lane_diff_max:
                return False
        if cfg.team_variance_max is not None:
            if self._raw(raw_breakdown, "team_variance", cfg) > cfg.team_variance_max:
                return False
        if cfg.minimum_main_role_ratio is not None:
            if self._main_role_ratio(teams) < cfg.minimum_main_role_ratio:
                return False
        return True

    def _raw(self, raw_breakdown: dict[str, float], name: str, cfg: HardConstraintConfig) -> float:
        """raw_breakdown only ever contains keys for Features the active
        Strategy actually enabled (see BalanceEvaluator.evaluate_raw) - a
        Strategy that disables one of these three Features while its
        HardConstraintConfig threshold for that same metric stays set would
        otherwise silently treat the missing value as 0.0, i.e. always
        "compliant," no matter how imbalanced the real (uncomputed) metric
        would have been. Failing loudly here instead of guessing 0.0 is
        cheap insurance since fixing the config mismatch (disable the
        threshold, or re-enable the Feature) is the operator's call, not
        something this layer should paper over."""
        if name not in raw_breakdown:
            raise ValueError(
                f"HardConstraintConfig has a threshold set for '{name}', but the active Strategy has "
                f"that Feature disabled - there's no raw value to check it against."
            )
        return raw_breakdown[name]

    def _is_structurally_valid(self, teams: list[Team]) -> bool:
        for team in teams:
            if len(team.players) != TEAM_SIZE:
                return False
            if team.slots is not None and {slot.position for slot in team.slots} != set(Position):
                return False
        return True

    def _main_role_ratio(self, teams: list[Team]) -> float:
        slots = [slot for team in teams if team.slots for slot in team.slots]
        if not slots:
            return 1.0
        main_count = sum(1 for slot in slots if slot.role_source == "main")
        return main_count / len(slots)
