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


def test_stable_prioritizes_team_variance_and_tier_distribution():
    config = StableStrategy().feature_config()
    assert config["team_variance"].weight >= config["average_rating"].weight
    assert config["tier_distribution"].weight >= config["role_penalty"].weight


def test_strategies_are_independent_instances_not_shared_state():
    a = CompetitiveStrategy().feature_config()
    b = CompetitiveStrategy().feature_config()
    assert a == b
    assert a is not b
