from __future__ import annotations

import dataclasses

from app.balance.balancer import TeamBalancer
from app.balance.execution_context import ExecutionContext
from app.balance.strategy import CompetitiveStrategy, StableStrategy
from app.models.player import Player
from app.position.signup import PlayerSignup
from app.utils.enums import Position, Tier


def _signups(count: int, ratings=None) -> list[PlayerSignup]:
    ratings = ratings or [1000 + i * 37 for i in range(count)]
    roles = list(Position)
    players = [
        Player(
            id=i + 1,
            nickname=f"p{i}",
            tier=Tier.GOLD,
            main_role=roles[i % len(roles)],
            official_rating=ratings[i],
        )
        for i in range(count)
    ]
    return [PlayerSignup(player=p) for p in players]


def test_run_returns_a_fully_populated_execution_context():
    balancer = TeamBalancer(strategy=StableStrategy())
    signups = _signups(10)

    context = balancer.run(signups, k=3)

    assert isinstance(context, ExecutionContext)
    assert context.input.execution_id
    assert context.input.strategy.name == "stable"
    assert context.input.search_policy.name == "stable"
    assert len(context.input.player_profiles) == 10
    assert len(context.input.role_preferences) == 10
    assert context.input.version_metadata.app_version
    assert context.input.version_metadata.feature_weights  # non-empty

    assert len(context.runtime.candidate_teams) >= 1
    assert context.runtime.search_statistics is not None
    assert context.runtime.search_statistics.nodes_expanded > 0
    assert context.runtime.search_statistics.elapsed_seconds >= 0.0
    assert len(context.runtime.constraint_results) == len(context.runtime.candidate_teams)
    assert all(cr.feasible for cr in context.runtime.constraint_results)
    assert len(context.runtime.feature_snapshots) == len(context.runtime.candidate_teams)

    assert context.result.top_recommendations == context.runtime.candidate_teams
    assert context.result.explain_data is not None
    assert set(context.result.explain_data.top_contributors.keys()) == set(context.runtime.feature_snapshots.keys())


def test_generate_teams_and_generate_top_teams_are_unchanged_thin_wrappers():
    balancer = TeamBalancer(strategy=StableStrategy())
    signups = _signups(10)

    single = balancer.generate_teams(signups)
    top = balancer.generate_top_teams(signups, k=3)

    assert single.cost == top[0].cost
    assert 1 <= len(top) <= 3


def test_context_is_immutable_mutating_a_field_requires_replace():
    balancer = TeamBalancer(strategy=StableStrategy())
    context = balancer.run(_signups(10), k=1)

    try:
        context.runtime.finished_at = None  # type: ignore[misc]
        assert False, "RuntimeContext should be frozen"
    except dataclasses.FrozenInstanceError:
        pass

    replaced = dataclasses.replace(context, result=dataclasses.replace(context.result, final_selection=1))
    assert replaced.result.final_selection == 1
    assert context.result.final_selection is None  # original untouched


def test_feature_snapshots_match_each_candidates_contributions():
    balancer = TeamBalancer(strategy=StableStrategy())
    context = balancer.run(_signups(10), k=3)

    for index, candidate in enumerate(context.runtime.candidate_teams):
        assert context.runtime.feature_snapshots[index] == candidate.contributions


def test_different_strategies_produce_matching_search_policy_names():
    stable_context = TeamBalancer(strategy=StableStrategy()).run(_signups(10), k=1)
    competitive_context = TeamBalancer(strategy=CompetitiveStrategy()).run(_signups(10), k=1)

    assert stable_context.input.search_policy.name == "stable"
    assert competitive_context.input.search_policy.name == "competitive"
    assert stable_context.input.version_metadata.strategy_name == "stable"
    assert competitive_context.input.version_metadata.strategy_name == "competitive"
