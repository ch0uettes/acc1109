from __future__ import annotations

import pytest

from app.balance.config import DEFAULT_FEATURE_CONFIG, FeatureConfig
from app.balance.features import (
    FEATURE_REGISTRY,
    BalanceEvaluator,
    FeatureRegistry,
    InternalRatingFeature,
    LaneBalanceFeature,
    MeanBalanceFeature,
    OutlierPenaltyFeature,
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


# --- MeanBalanceFeature: 전체 평균 균형 - stddev of team averages
# around the global mean, considered together. ---


def test_mean_balance_feature():
    team_a = Team(index=0, players=[_player(100), _player(100)])
    team_b = Team(index=1, players=[_player(200), _player(200)])
    # final_rating blends official_rating with internal_rating (0 here) at
    # the brand-new-player weight (0.9 base / 0.1 internal by default), so
    # team averages are 90 and 180 - stddev of two points is half their
    # gap (population stdev, not sample).
    assert MeanBalanceFeature().evaluate_raw([team_a, team_b]) == 45.0


def test_mean_balance_feature_normalizes_via_smooth_logistic_curve():
    # No single raw value flips the score from "low" to "high" - values
    # just below and just above the midpoint score nearly the same,
    # unlike a hard threshold (see LogisticNormalizer's docstring).
    feature = MeanBalanceFeature()
    below = feature.normalize(159.0)
    above = feature.normalize(161.0)
    assert below == pytest.approx(above, abs=0.01)
    assert feature.normalize(0.0) < feature.normalize(160.0) < feature.normalize(800.0)


def test_team_variance_feature_zero_when_equal_spread():
    team_a = Team(index=0, players=[_player(100), _player(300)])
    team_b = Team(index=1, players=[_player(150), _player(250)])
    value = TeamVarianceFeature().evaluate_raw([team_a, team_b])
    assert value >= 0


def test_team_variance_feature_averages_per_team_variance_not_a_cross_team_gap():
    # A single messy team should be penalized on its own merits - the
    # OTHER team being equally messy or perfectly uniform shouldn't
    # change how bad the first team's own spread is judged.
    messy = Team(index=0, players=[_player(2500), _player(2100), _player(1800), _player(1400), _player(900)])
    uniform = Team(index=1, players=[_player(1800), _player(1790), _player(1810), _player(1785), _player(1805)])

    messy_alone = TeamVarianceFeature().evaluate_raw([messy, messy])
    mixed = TeamVarianceFeature().evaluate_raw([messy, uniform])

    # Averaging per-team variance means pairing the messy team with a
    # uniform one should score roughly half of pairing it with another
    # messy team - not zero, and not dominated by a cross-team gap.
    assert mixed == pytest.approx(messy_alone / 2, rel=0.05)


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
    # RMS over a single lane is just that lane's own gap.
    assert LaneBalanceFeature().evaluate_raw([team_a, team_b]) == pytest.approx(
        top_a.final_rating - top_b.final_rating
    )


def test_lane_balance_feature_uses_rms_not_sum_across_lanes():
    # One catastrophic lane (1000) should score much worse than 5 mild,
    # nearly-equal-sum lanes (220 each) - a plain sum treats these almost
    # identically (1080 vs 1100); RMS should not.
    def _team(index: int, gaps: list[float]) -> tuple[Team, Team]:
        team_a_players, team_a_slots = [], []
        team_b_players, team_b_slots = [], []
        for position, gap in zip(Position, gaps):
            hi, lo = _player(1000 + gap), _player(1000)
            team_a_players.append(hi)
            team_a_slots.append(_slot(hi, position))
            team_b_players.append(lo)
            team_b_slots.append(_slot(lo, position))
        return (
            Team(index=index, players=team_a_players, slots=team_a_slots),
            Team(index=index + 1, players=team_b_players, slots=team_b_slots),
        )

    one_bad_lane_a, one_bad_lane_b = _team(0, [1000, 20, 20, 20, 20])
    uniform_a, uniform_b = _team(2, [220, 220, 220, 220, 220])

    one_bad_lane_score = LaneBalanceFeature().evaluate_raw([one_bad_lane_a, one_bad_lane_b])
    uniform_score = LaneBalanceFeature().evaluate_raw([uniform_a, uniform_b])

    assert one_bad_lane_score > uniform_score  # a plain sum would call these ~equal (1080 vs 1100)


def test_lane_balance_feature_normalizes_linearly():
    feature = LaneBalanceFeature()
    assert feature.normalize(0.0) == 0.0
    assert feature.normalize(10_000.0) == 1.0  # clipped


# --- OutlierPenaltyFeature: 극단적인 팀 생성 방지 - the single WORST
# team's absolute deviation from the global mean, isolated from every
# other team's own spread (that's MeanBalanceFeature's job). ---


def test_outlier_penalty_feature_computes_max_absolute_deviation():
    team_a = Team(index=0, players=[_player(100), _player(100)])  # avg final_rating 90
    team_b = Team(index=1, players=[_player(200), _player(200)])  # avg final_rating 180
    # mean=135, deviations +-45 -> max absolute deviation is 45
    assert OutlierPenaltyFeature().evaluate_raw([team_a, team_b]) == pytest.approx(45.0)


def test_outlier_penalty_feature_zero_when_all_team_averages_equal():
    team_a = Team(index=0, players=[_player(100), _player(200)])
    team_b = Team(index=1, players=[_player(150), _player(150)])
    assert OutlierPenaltyFeature().evaluate_raw([team_a, team_b]) == pytest.approx(0.0)


def test_outlier_penalty_feature_punishes_a_single_outlier_more_than_an_even_spread():
    # Same overall range (100 to 400 in both cases), but concentrated in
    # ONE team vs graduated evenly across all teams - a single true
    # outlier should score worse, since outlier_penalty isolates the
    # single worst team rather than reflecting the whole distribution.
    one_outlier = [Team(index=i, players=[_player(v), _player(v)]) for i, v in enumerate([100, 100, 100, 400])]
    evenly_spread = [Team(index=i, players=[_player(v), _player(v)]) for i, v in enumerate([100, 200, 300, 400])]

    outlier_penalty = OutlierPenaltyFeature().evaluate_raw(one_outlier)
    spread_penalty = OutlierPenaltyFeature().evaluate_raw(evenly_spread)

    assert outlier_penalty > spread_penalty


def test_outlier_penalty_feature_normalizes_sharply_via_logistic_curve():
    feature = OutlierPenaltyFeature()
    assert feature.normalize(0.0) < feature.normalize(300.0) < feature.normalize(1000.0)
    below = feature.normalize(299.0)
    above = feature.normalize(301.0)
    assert below == pytest.approx(above, abs=0.01)


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

    breakdown = BalanceEvaluator().evaluate_raw([team_a, team_b], [MeanBalanceFeature()])

    assert breakdown == {"mean_balance": pytest.approx(45.0)}


def test_balance_evaluator_normalize_delegates_to_each_features_own_normalizer():
    # BalanceEvaluator does no normalization math itself - it just routes
    # each raw value to the Feature instance that produced it.
    raw = {"mean_balance": 400.0}
    normalized = BalanceEvaluator().normalize(raw, [MeanBalanceFeature()])
    assert normalized["mean_balance"] == pytest.approx(MeanBalanceFeature().normalize(400.0))


def test_balance_evaluator_combine_applies_strategy_weight_to_normalized_values():
    strategy = _FixedWeightStrategy({"mean_balance": FeatureConfig(enabled=True, weight=2.0)})
    total = BalanceEvaluator().combine({"mean_balance": 0.5}, strategy)
    assert total == pytest.approx(1.0)


def test_balance_evaluator_combine_skips_features_the_strategy_weighs_zero():
    strategy = _FixedWeightStrategy({"mean_balance": FeatureConfig(enabled=True, weight=0.0)})
    total = BalanceEvaluator().combine({"mean_balance": 0.9}, strategy)
    assert total == 0.0


# --- BalanceEvaluator.explain(): Raw -> Normalized -> Weight ->
# Contribution audit trail per Feature, for "why did this combo win" /
# "why did this Feature dominate" debugging (see team_page.py's UI). ---


def test_explain_reports_the_full_raw_normalized_weight_contribution_chain():
    strategy = _FixedWeightStrategy(
        {"mean_balance": FeatureConfig(enabled=True, weight=0.5), "lane_balance": FeatureConfig(enabled=True, weight=0.5)}
    )
    raw = {"mean_balance": 200.0, "lane_balance": 400.0}
    normalized = {"mean_balance": 0.2, "lane_balance": 0.6}

    contributions = BalanceEvaluator().explain(raw, normalized, strategy)
    by_name = {c.name: c for c in contributions}

    assert by_name["mean_balance"].raw == 200.0
    assert by_name["mean_balance"].normalized == 0.2
    assert by_name["mean_balance"].weight == 0.5
    assert by_name["mean_balance"].contribution == pytest.approx(0.1)
    assert by_name["lane_balance"].contribution == pytest.approx(0.3)

    total = 0.1 + 0.3
    assert by_name["mean_balance"].contribution_pct == pytest.approx(0.1 / total * 100)
    assert by_name["lane_balance"].contribution_pct == pytest.approx(0.3 / total * 100)


def test_explain_sorts_contributions_descending():
    strategy = _FixedWeightStrategy(
        {"mean_balance": FeatureConfig(enabled=True, weight=0.1), "lane_balance": FeatureConfig(enabled=True, weight=0.9)}
    )
    raw = {"mean_balance": 100.0, "lane_balance": 100.0}
    normalized = {"mean_balance": 0.5, "lane_balance": 0.5}

    contributions = BalanceEvaluator().explain(raw, normalized, strategy)

    assert [c.name for c in contributions] == ["lane_balance", "mean_balance"]


def test_explain_contribution_pct_is_zero_when_total_cost_is_zero():
    strategy = _FixedWeightStrategy({"mean_balance": FeatureConfig(enabled=True, weight=0.5)})
    contributions = BalanceEvaluator().explain({"mean_balance": 100.0}, {"mean_balance": 0.0}, strategy)
    assert contributions[0].contribution_pct == 0.0


def test_balance_evaluator_does_not_know_feature_count_ahead_of_time():
    # Same evaluator instance, two completely different feature lists -
    # it has no internal notion of "how many Features exist".
    evaluator = BalanceEvaluator()
    team_a = Team(index=0, players=[_player(100)])
    team_b = Team(index=1, players=[_player(200)])

    breakdown_one = evaluator.evaluate_raw([team_a, team_b], [MeanBalanceFeature()])
    breakdown_two = evaluator.evaluate_raw(
        [team_a, team_b], [MeanBalanceFeature(), TeamVarianceFeature()]
    )

    assert set(breakdown_one.keys()) == {"mean_balance"}
    assert set(breakdown_two.keys()) == {"mean_balance", "team_variance"}


# --- FeatureRegistry: registration/lookup/category/metadata/removal ---


def test_feature_registry_register_and_get():
    registry = FeatureRegistry()
    registry.register(MeanBalanceFeature)
    assert registry.get("mean_balance") is MeanBalanceFeature
    assert "mean_balance" in registry.names()


def test_feature_registry_unregister():
    registry = FeatureRegistry()
    registry.register(MeanBalanceFeature)
    registry.unregister("mean_balance")
    assert "mean_balance" not in registry.names()


def test_feature_registry_by_category():
    registry = FeatureRegistry()
    registry.register(MeanBalanceFeature)
    registry.register(InternalRatingFeature)
    registry.register(LaneBalanceFeature)
    assert set(registry.by_category("rating")) == {"mean_balance", "internal_rating"}
    assert registry.by_category("lane") == ["lane_balance"]


def test_feature_registry_metadata_reflects_feature_class():
    registry = FeatureRegistry()
    registry.register(LaneBalanceFeature)
    meta = registry.metadata("lane_balance")
    assert meta.category == "lane"
    assert meta.default_weight == 0.20
    assert meta.default_enabled is True


def test_feature_registry_get_active_features_respects_strategy():
    registry = FeatureRegistry()
    registry.register(MeanBalanceFeature)
    registry.register(TeamVarianceFeature)
    strategy = _FixedWeightStrategy(
        {
            "mean_balance": FeatureConfig(enabled=True, weight=1.0),
            "team_variance": FeatureConfig(enabled=False, weight=1.0),
        }
    )
    active = registry.get_active_features(strategy)
    assert [f.name for f in active] == ["mean_balance"]


def test_new_feature_registers_without_touching_evaluator_or_registry_code():
    """Proves the ①구현 ②등록 ③Strategy Config 흐름: a brand-new Feature
    plugs in with zero edits to BalanceEvaluator or FeatureRegistry."""

    class DummyFeature(MeanBalanceFeature):
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
    assert names == {"mean_balance", "team_variance"}


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
