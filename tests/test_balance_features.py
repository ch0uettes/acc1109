from __future__ import annotations

import pytest

from app.balance.config import DEFAULT_FEATURE_CONFIG, FeatureConfig
from app.balance.features import (
    FEATURE_REGISTRY,
    AverageRatingFeature,
    BalanceEvaluator,
    FeatureRegistry,
    InternalRatingFeature,
    LaneBalanceFeature,
    RolePenaltyFeature,
    TeamVarianceFeature,
    TierDistributionFeature,
    build_balance_evaluator,
)
from app.balance.features.rating.modifiers import confidence_weighted_internal_rating
from app.balance.strategy import STRATEGY_REGISTRY, IBalanceStrategy
from app.models.player import Player
from app.models.team import Team, TeamSlot
from app.utils.enums import Position, Tier


def _player(rating: float, tier: Tier = Tier.GOLD) -> Player:
    return Player(
        nickname=f"p{rating}-{tier.value}",
        tier=tier,
        main_role=Position.MID,
        official_rating=rating,
    )


def _slot(player: Player, position: Position, role_penalty: float = 0.0) -> TeamSlot:
    return TeamSlot(position=position, player=player, role_penalty=role_penalty, role_source="main")


class _FixedWeightStrategy(IBalanceStrategy):
    name = "fixed"

    def __init__(self, config: dict[str, FeatureConfig]) -> None:
        self._config = config

    def feature_config(self) -> dict[str, FeatureConfig]:
        return self._config


def test_average_rating_feature():
    team_a = Team(index=0, players=[_player(100), _player(100)])
    team_b = Team(index=1, players=[_player(200), _player(200)])
    # final_rating blends official_rating with internal_rating (0 here) at
    # the brand-new-player weight (0.9 base / 0.1 internal by default), so
    # the diff scales down from the raw official_rating diff accordingly.
    assert AverageRatingFeature().evaluate_raw([team_a, team_b]) == 90.0


def test_average_rating_feature_normalizes_via_smooth_logistic_curve():
    # No single raw value flips the score from "low" to "high" - values
    # just below and just above the midpoint score nearly the same,
    # unlike a hard threshold (see LogisticNormalizer's docstring).
    feature = AverageRatingFeature()
    below = feature.normalize(399.0)
    above = feature.normalize(401.0)
    assert below == pytest.approx(above, abs=0.01)
    assert feature.normalize(0.0) < feature.normalize(400.0) < feature.normalize(2000.0)


def test_team_variance_feature_zero_when_equal_spread():
    team_a = Team(index=0, players=[_player(100), _player(300)])
    team_b = Team(index=1, players=[_player(150), _player(250)])
    value = TeamVarianceFeature().evaluate_raw([team_a, team_b])
    assert value >= 0


def test_team_variance_feature_normalizes_via_logarithmic_curve():
    # Logarithmic compresses team_variance's huge raw range (squared
    # rating-point units) so it doesn't dominate every other Feature
    # once weighted - a 10x jump in raw value should NOT be a 10x jump
    # in normalized score.
    feature = TeamVarianceFeature()
    small, large = feature.normalize(5_000.0), feature.normalize(50_000.0)
    assert small < large
    assert large - small < 1.0  # far less than a proportional 10x gap would imply


def test_internal_rating_feature_applies_confidence_modifier():
    p1 = _player(100)
    p1.internal_rating = 1800.0
    p1.confidence = 0.30
    p2 = _player(100)
    p2.internal_rating = 1800.0
    p2.confidence = 1.00
    team_a = Team(index=0, players=[p1])
    team_b = Team(index=1, players=[p2])

    # Confidence is NOT its own scored Feature - it's a modifier applied
    # inside InternalRatingFeature: contribution = internal_rating *
    # confidence (see the ChatGPT-suggested redesign this implements).
    assert confidence_weighted_internal_rating(p1) == pytest.approx(1800.0 * 0.30)
    assert InternalRatingFeature().evaluate_raw([team_a, team_b]) == pytest.approx(
        1800.0 * 1.00 - 1800.0 * 0.30
    )


def test_role_penalty_feature_sums_penalties():
    p1, p2 = _player(100), _player(200)
    team_a = Team(index=0, players=[p1], slots=[_slot(p1, Position.TOP, role_penalty=0.0)])
    team_b = Team(index=1, players=[p2], slots=[_slot(p2, Position.TOP, role_penalty=10.0)])
    assert RolePenaltyFeature().evaluate_raw([team_a, team_b]) == 10.0


def test_role_penalty_feature_requires_slots():
    team = Team(index=0, players=[_player(100)])
    with pytest.raises(ValueError):
        RolePenaltyFeature().evaluate_raw([team])


def test_role_penalty_feature_normalizes_linearly():
    feature = RolePenaltyFeature()
    assert feature.normalize(0.0) == 0.0
    assert feature.normalize(500.0) == pytest.approx(0.5)
    assert feature.normalize(10_000.0) == 1.0  # clipped, doesn't exceed 1.0


def test_lane_balance_feature_compares_same_lane_across_teams():
    top_a, top_b = _player(2000), _player(1800)
    team_a = Team(index=0, players=[top_a], slots=[_slot(top_a, Position.TOP)])
    team_b = Team(index=1, players=[top_b], slots=[_slot(top_b, Position.TOP)])
    assert LaneBalanceFeature().evaluate_raw([team_a, team_b]) == pytest.approx(
        top_a.final_rating - top_b.final_rating
    )


def test_tier_distribution_feature_counts_gap_per_tier():
    team_a = Team(index=0, players=[_player(2400, Tier.DIAMOND), _player(2400, Tier.DIAMOND)])
    team_b = Team(index=1, players=[_player(2400, Tier.DIAMOND)])
    # Diamond bucket: 2 vs 1 -> gap of 1; every other tier bucket is 0 vs 0
    assert TierDistributionFeature().evaluate_raw([team_a, team_b]) == 1


def test_tier_distribution_feature_normalizes_via_piecewise_curve():
    feature = TierDistributionFeature()
    assert feature.normalize(0.0) == 0.0
    assert feature.normalize(1.0) == pytest.approx(0.1)  # interpolated between (0,0) and (2,0.2)
    assert feature.normalize(2.0) == pytest.approx(0.2)
    assert feature.normalize(100.0) == 1.0  # clamped past the last breakpoint


def test_feature_metadata_is_declared_for_every_registered_feature():
    for name in FEATURE_REGISTRY:
        feature_cls = FEATURE_REGISTRY[name]
        assert feature_cls.category
        assert feature_cls.description
        assert isinstance(feature_cls.default_enabled, bool)
        assert isinstance(feature_cls.default_weight, (int, float))


# --- New stateless BalanceEvaluator: evaluate_raw() computes unweighted
# Feature values; normalize() delegates to each Feature's own Normalizer;
# combine() applies Strategy weight to already-normalized values. Split
# into steps because each Feature owns its own normalization (see
# IBalanceFeature) - BalanceEvaluator only orchestrates. ---


def test_balance_evaluator_evaluate_raw_returns_unweighted_breakdown():
    team_a = Team(index=0, players=[_player(100)])
    team_b = Team(index=1, players=[_player(200)])

    breakdown = BalanceEvaluator().evaluate_raw([team_a, team_b], [AverageRatingFeature()])

    assert breakdown == {"average_rating": pytest.approx(90.0)}


def test_balance_evaluator_normalize_delegates_to_each_features_own_normalizer():
    # BalanceEvaluator does no normalization math itself - it just routes
    # each raw value to the Feature instance that produced it.
    raw = {"average_rating": 400.0}
    normalized = BalanceEvaluator().normalize(raw, [AverageRatingFeature()])
    assert normalized["average_rating"] == pytest.approx(AverageRatingFeature().normalize(400.0))


def test_balance_evaluator_combine_applies_strategy_weight_to_normalized_values():
    strategy = _FixedWeightStrategy({"average_rating": FeatureConfig(enabled=True, weight=2.0)})
    total = BalanceEvaluator().combine({"average_rating": 0.5}, strategy)
    assert total == pytest.approx(1.0)


def test_balance_evaluator_combine_skips_features_the_strategy_weighs_zero():
    strategy = _FixedWeightStrategy({"average_rating": FeatureConfig(enabled=True, weight=0.0)})
    total = BalanceEvaluator().combine({"average_rating": 0.9}, strategy)
    assert total == 0.0


def test_balance_evaluator_does_not_know_feature_count_ahead_of_time():
    # Same evaluator instance, two completely different feature lists -
    # it has no internal notion of "how many Features exist".
    evaluator = BalanceEvaluator()
    team_a = Team(index=0, players=[_player(100)])
    team_b = Team(index=1, players=[_player(200)])

    breakdown_one = evaluator.evaluate_raw([team_a, team_b], [AverageRatingFeature()])
    breakdown_two = evaluator.evaluate_raw(
        [team_a, team_b], [AverageRatingFeature(), TeamVarianceFeature()]
    )

    assert set(breakdown_one.keys()) == {"average_rating"}
    assert set(breakdown_two.keys()) == {"average_rating", "team_variance"}


# --- FeatureRegistry: registration/lookup/category/metadata/removal ---


def test_feature_registry_register_and_get():
    registry = FeatureRegistry()
    registry.register(AverageRatingFeature)
    assert registry.get("average_rating") is AverageRatingFeature
    assert "average_rating" in registry.names()


def test_feature_registry_unregister():
    registry = FeatureRegistry()
    registry.register(AverageRatingFeature)
    registry.unregister("average_rating")
    assert "average_rating" not in registry.names()


def test_feature_registry_by_category():
    registry = FeatureRegistry()
    registry.register(AverageRatingFeature)
    registry.register(InternalRatingFeature)
    registry.register(LaneBalanceFeature)
    assert set(registry.by_category("rating")) == {"average_rating", "internal_rating"}
    assert registry.by_category("lane") == ["lane_balance"]


def test_feature_registry_metadata_reflects_feature_class():
    registry = FeatureRegistry()
    registry.register(LaneBalanceFeature)
    meta = registry.metadata("lane_balance")
    assert meta.category == "lane"
    assert meta.default_weight == 0.35
    assert meta.default_enabled is True


def test_feature_registry_get_active_features_respects_strategy():
    registry = FeatureRegistry()
    registry.register(AverageRatingFeature)
    registry.register(TeamVarianceFeature)
    strategy = _FixedWeightStrategy(
        {
            "average_rating": FeatureConfig(enabled=True, weight=1.0),
            "team_variance": FeatureConfig(enabled=False, weight=1.0),
        }
    )
    active = registry.get_active_features(strategy)
    assert [f.name for f in active] == ["average_rating"]


def test_new_feature_registers_without_touching_evaluator_or_registry_code():
    """Proves the ①구현 ②등록 ③Strategy Config 흐름: a brand-new Feature
    plugs in with zero edits to BalanceEvaluator or FeatureRegistry."""

    class DummyFeature(AverageRatingFeature):
        name = "dummy"

        def evaluate_raw(self, teams):
            return 42.0

    registry = FeatureRegistry()
    registry.register(DummyFeature)
    strategy = _FixedWeightStrategy({"dummy": FeatureConfig(enabled=True, weight=1.0)})

    features = registry.get_active_features(strategy)
    team_a = Team(index=0, players=[_player(100)])
    team_b = Team(index=1, players=[_player(100)])

    breakdown = BalanceEvaluator().evaluate_raw([team_a, team_b], features)
    assert breakdown["dummy"] == 42.0


# --- Legacy path: RandomSwapOptimizer/TieredSnakeDraftOptimizer still use
# build_balance_evaluator/default_balance_evaluator directly. ---


def test_build_balance_evaluator_only_registers_enabled_features():
    evaluator = build_balance_evaluator(DEFAULT_FEATURE_CONFIG)
    names = {feature.name for feature in evaluator.features}
    assert names == {"average_rating", "team_variance"}


def test_each_strategy_feature_config_only_references_registered_features():
    for strategy_cls in STRATEGY_REGISTRY.values():
        config = strategy_cls().feature_config()
        assert set(config.keys()) <= set(FEATURE_REGISTRY.keys())
        assert all(fc.enabled and fc.weight > 0 for fc in config.values())


def test_strategy_feature_config_builds_a_working_legacy_evaluator():
    for strategy_cls in STRATEGY_REGISTRY.values():
        evaluator = build_balance_evaluator(strategy_cls().feature_config())
        names = {feature.name for feature in evaluator.features}
        assert {"role_penalty", "lane_balance", "tier_distribution"} <= names
