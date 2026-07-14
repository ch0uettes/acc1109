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
    "average_rating": FeatureConfig(enabled=True, weight=1.0),
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

    # average_rating is now stddev-of-team-averages (not max-min), which
    # runs noticeably smaller in raw magnitude than max-min did for the
    # same distribution (empirically ~1/2.5x for a 4-team split) - the
    # midpoint/steepness are recalibrated accordingly, not just copied
    # from the old max-min-era defaults.
    average_rating_midpoint: float = 160.0
    average_rating_steepness: float = 0.0184
    internal_rating_midpoint: float = 400.0
    internal_rating_steepness: float = 0.0075
    # lane_difference is now an RMS of per-lane gaps (not a sum), so its
    # raw scale sits closer to a single bad lane's gap rather than 5x
    # that - recalibrated down from the old sum-based ceiling.
    lane_difference_max: float = 2500.0
    team_variance_scale: float = 200_000.0
    # variance (not stddev) of team averages - squares deviations, so a
    # single team far from the mean is penalized much harder than the
    # same gap spread evenly across teams (see InterTeamBalanceFeature).
    inter_team_balance_scale: float = 200_000.0
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

    average_rating_diff_max: float | None = None
    lane_diff_max: float | None = None
    team_variance_max: float | None = None
    minimum_main_role_ratio: float | None = None


DEFAULT_HARD_CONSTRAINT_CONFIG = HardConstraintConfig()
