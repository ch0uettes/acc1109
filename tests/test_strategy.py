from __future__ import annotations

from app.balance.strategy import (
    DEFAULT_STRATEGY,
    STRATEGY_REGISTRY,
    ComfortStrategy,
    CompetitiveStrategy,
    StableStrategy,
)


def test_strategy_registry_has_all_three_modes():
    assert set(STRATEGY_REGISTRY.keys()) == {"competitive", "comfort", "stable"}
    assert STRATEGY_REGISTRY["competitive"] is CompetitiveStrategy
    assert STRATEGY_REGISTRY["comfort"] is ComfortStrategy
    assert STRATEGY_REGISTRY["stable"] is StableStrategy


def test_default_strategy_is_stable():
    assert isinstance(DEFAULT_STRATEGY, StableStrategy)


def test_competitive_prioritizes_lane_balance_over_role_penalty():
    config = CompetitiveStrategy().feature_config()
    assert config["lane_balance"].weight > config["role_penalty"].weight


def test_comfort_prioritizes_role_penalty_over_lane_balance():
    config = ComfortStrategy().feature_config()
    assert config["role_penalty"].weight > config["lane_balance"].weight


def test_stable_prioritizes_mean_balance_over_team_variance():
    # mean_balance (cross-team parity) must never be outweighed by
    # team_variance (within-team homogeneity) - team_variance rewarding
    # "similar tiers clustered on the same team" can otherwise win out
    # over closer cross-team averages, which is backwards: team_variance
    # is meant to break ties among already-close-average splits, not
    # override average parity.
    config = StableStrategy().feature_config()
    assert config["mean_balance"].weight >= config["team_variance"].weight
    assert config["tier_distribution"].weight >= config["role_penalty"].weight


def test_every_strategy_weighs_cross_team_measures_above_within_team_variance():
    # outlier_penalty/mean_balance both measure cross-team average
    # parity (one isolates the single worst team, one looks at the whole
    # distribution); team_variance measures within-team homogeneity
    # only. The combined cross-team weight must clearly outweigh
    # team_variance in every Strategy, or clustering similar tiers onto
    # the same team can structurally win over genuinely balanced
    # cross-team splits.
    for strategy_cls in STRATEGY_REGISTRY.values():
        config = strategy_cls().feature_config()
        cross_team_weight = config["outlier_penalty"].weight + config["mean_balance"].weight
        assert cross_team_weight > config["team_variance"].weight


def test_strategies_are_independent_instances_not_shared_state():
    a = CompetitiveStrategy().feature_config()
    b = CompetitiveStrategy().feature_config()
    assert a == b
    assert a is not b
