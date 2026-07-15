from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RolePenaltyConfig:
    """Cost of assigning a player to a lane that isn't their resolved
    Main role. `other` must stay far larger than `main`/`sub` combined for
    PositionAssigner's hard constraint to hold in practice - see
    app/position/assigner.py."""

    main: float = 0.0
    sub: float = 10.0
    other: float = 100.0


DEFAULT_ROLE_PENALTY_CONFIG = RolePenaltyConfig()


@dataclass(frozen=True)
class FeatureConfig:
    """Whether one IBalanceFeature runs at all, and how heavily it counts
    when it does. Keyed by feature name in a plain dict (not a fixed
    dataclass field) so adding a new Feature is purely additive - one new
    dict entry, never a change to this file's structure or to
    BalanceEvaluator. Disabling a feature (enabled=False) is the primary
    on/off switch; weight=0 has the same practical effect and remains a
    secondary guard against a feature being registered directly without
    going through config."""

    enabled: bool = True
    weight: float = 1.0


# Rating-only features are on by default, matching the legacy
# RandomSwapOptimizer/TieredSnakeDraftOptimizer pipeline (which never
# populates Team.slots, so position-aware features would just raise).
# The position-aware pipeline (TeamBalancer + TeamSearchEngine +
# PositionAssigner) doesn't use this constant at all - it builds its
# config from an IBalanceStrategy instead (see app/balance/strategy.py),
# which is the one true "which features, how heavily" source for that
# pipeline. This dict exists purely to keep the legacy optimizers' tests
# working exactly as before.
DEFAULT_FEATURE_CONFIG: dict[str, FeatureConfig] = {
    "mean_balance": FeatureConfig(enabled=True, weight=1.0),
    "team_variance": FeatureConfig(enabled=True, weight=0.5),
    "role_penalty": FeatureConfig(enabled=False, weight=1.0),
    "lane_balance": FeatureConfig(enabled=False, weight=1.0),
    "tier_distribution": FeatureConfig(enabled=False, weight=1.0),
    "internal_rating": FeatureConfig(enabled=False, weight=0.0),
    "recent_form": FeatureConfig(enabled=False, weight=0.0),
    "synergy": FeatureConfig(enabled=False, weight=0.0),
    "penalty": FeatureConfig(enabled=False, weight=0.0),
}


@dataclass(frozen=True)
class NormalizationConfig:
    """Thresholds/params behind every Feature's own Normalizer (see
    app/balance/features/scaling.py) - never hardcoded inside a Feature
    class, per the "Config 기반 Threshold" requirement. Each Feature owns
    exactly the fields it needs; nothing here is shared/reused across
    Features by accident.

    Defaults are calibrated to this app's rating scale (Tier steps of
    400, Division steps of 100 - see app/rating/official.py). They're a
    starting point, not a guarantee of "correct" - tune per server if a
    community's real rating spread differs."""

    # mean_balance is stddev-of-team-averages around the global mean -
    # empirically runs ~1/2.5x smaller in raw magnitude than the old
    # max-min measure did for the same distribution, so midpoint/
    # steepness are calibrated for that scale, not copied from max-min.
    mean_balance_midpoint: float = 160.0
    mean_balance_steepness: float = 0.0184
    internal_rating_midpoint: float = 400.0
    internal_rating_steepness: float = 0.0075
    # lane_difference is an RMS of per-lane gaps (not a sum), so its raw
    # scale sits closer to a single bad lane's gap rather than 5x that.
    lane_difference_max: float = 2500.0
    # team_variance is now the AVERAGE of each team's own internal
    # variance (not a max-min gap between teams' variances), which runs
    # much larger in raw magnitude for the same roster - recalibrated up
    # roughly 20x from the old gap-based scale so a typical mixed-tier
    # team (variance in the several-hundred-thousand range) doesn't
    # saturate the Normalizer at 1.0 for every candidate.
    team_variance_scale: float = 4_000_000.0
    # outlier_penalty is the single worst team's absolute deviation from
    # the global mean (not every team's spread) - a linear rating-point
    # unit, so it gets a Logistic curve like mean_balance, calibrated to
    # ramp up sharply (per the PRD's "Outlier가 있으면 Penalty가 급격히
    # 증가해야 한다") rather than mean_balance's gentler slope.
    outlier_penalty_midpoint: float = 300.0
    outlier_penalty_steepness: float = 0.01
    tier_distribution_breakpoints: tuple[tuple[float, float], ...] = (
        (0.0, 0.0),
        (2.0, 0.2),
        (5.0, 0.5),
        (10.0, 0.8),
        (20.0, 1.0),
    )
    role_penalty_max: float = 1000.0


DEFAULT_NORMALIZATION_CONFIG = NormalizationConfig()


@dataclass(frozen=True)
class HardConstraintConfig:
    """Config-driven Hard Constraint thresholds (Feasibility Check layer
    - see app/balance/constraints.py). Defaults are intentionally
    permissive (every raw threshold is None, meaning "never reject on
    this") - aggressive numeric Hard Constraints create cliff-edge
    behavior (average rating gap 801 rejected, 799 passes) that this
    project's balancing philosophy explicitly avoids in favor of Soft
    Penalty (normalized + weighted Features) doing the real ranking.
    Tighten a field only when an operator genuinely wants to hard-exclude
    certain splits for one server/event."""

    mean_balance_diff_max: float | None = None
    lane_diff_max: float | None = None
    team_variance_max: float | None = None
    minimum_main_role_ratio: float | None = None


DEFAULT_HARD_CONSTRAINT_CONFIG = HardConstraintConfig()
