from __future__ import annotations

from app.balance.constraint_engine.context import ConstraintContext
from app.balance.constraint_engine.plugins.role import FixedRoleCollisionConstraint, FixedRoleConstraint
from app.balance.constraint_engine.plugins.structural import (
    RequiredRoleConstraint,
    TeamSizeConstraint,
    UniquePlayerConstraint,
)
from app.balance.constraint_engine.result import ConstraintStatus
from app.balance.search_engine import BacktrackingSearchEngine
from app.balance.strategy import StableStrategy
from app.balance.search_policy import StableSearchPolicy
from app.models.player import Player
from app.models.team import Team, TeamSlot
from app.position.preference_manager import RolePreferenceManager
from app.position.schemas import RolePreference
from app.utils.enums import Position, Tier


def _player(pid: int, rating: float, role: Position = Position.MID) -> Player:
    return Player(id=pid, nickname=f"p{pid}", tier=Tier.GOLD, main_role=role, official_rating=rating)


def _leaf_context(teams, override_player_ids=frozenset()) -> ConstraintContext:
    from types import MappingProxyType

    return ConstraintContext(
        rosters=tuple(tuple(t.players) for t in teams),
        team_index=None,
        candidate_player=None,
        teams=tuple(teams),
        player_profiles=tuple(p for t in teams for p in t.players),
        role_preferences=MappingProxyType({}),
        strategy=StableStrategy(),
        search_policy=StableSearchPolicy(),
        constraint_priorities=MappingProxyType({}),
        override_player_ids=override_player_ids,
    )


def _team_with_slot(role_source: str) -> Team:
    player = _player(1, 1000)
    slot = TeamSlot(position=Position.SUPPORT, player=player, role_penalty=0.0, role_source=role_source)
    return Team(index=0, players=[player], slots=[slot])


def _partial_context(
    rosters: list[list[Player]],
    team_index: int,
    candidate: Player,
    role_preferences: dict,
    override_player_ids=frozenset(),
) -> ConstraintContext:
    from types import MappingProxyType

    return ConstraintContext(
        rosters=tuple(tuple(r) for r in rosters),
        team_index=team_index,
        candidate_player=candidate,
        teams=None,
        player_profiles=tuple(p for r in rosters for p in r) + (candidate,),
        role_preferences=MappingProxyType(role_preferences),
        strategy=StableStrategy(),
        search_policy=StableSearchPolicy(),
        constraint_priorities=MappingProxyType({}),
        override_player_ids=override_player_ids,
    )


def test_team_size_constraint_fails_when_team_has_wrong_player_count():
    team = Team(index=0, players=[_player(i, 1000) for i in range(4)], slots=None)
    result = TeamSizeConstraint().evaluate(_leaf_context([team]))
    assert result.status == ConstraintStatus.FAIL


def test_team_size_constraint_passes_for_five_players():
    team = Team(index=0, players=[_player(i, 1000) for i in range(5)], slots=None)
    result = TeamSizeConstraint().evaluate(_leaf_context([team]))
    assert result.status == ConstraintStatus.PASS


def test_unique_player_constraint_fails_on_duplicate_across_teams():
    shared = _player(1, 1000)
    team_a = Team(index=0, players=[shared], slots=None)
    team_b = Team(index=1, players=[shared], slots=None)
    result = UniquePlayerConstraint().evaluate(_leaf_context([team_a, team_b]))
    assert result.status == ConstraintStatus.FAIL


def test_required_role_constraint_fails_when_position_missing():
    player = _player(1, 1000)
    slot = TeamSlot(position=Position.TOP, player=player, role_penalty=0.0, role_source="main")
    team = Team(index=0, players=[player], slots=[slot])
    result = RequiredRoleConstraint().evaluate(_leaf_context([team]))
    assert result.status == ConstraintStatus.FAIL


def test_fixed_role_constraint_passes_with_no_overrides():
    team = _team_with_slot(role_source="other")
    result = FixedRoleConstraint().evaluate(_leaf_context([team], override_player_ids=frozenset()))
    assert result.status == ConstraintStatus.PASS


def test_fixed_role_constraint_fails_when_override_not_honored():
    team = _team_with_slot(role_source="other")
    result = FixedRoleConstraint().evaluate(_leaf_context([team], override_player_ids=frozenset({1})))
    assert result.status == ConstraintStatus.FAIL


def test_fixed_role_constraint_passes_when_override_honored():
    team = _team_with_slot(role_source="main")
    result = FixedRoleConstraint().evaluate(_leaf_context([team], override_player_ids=frozenset({1})))
    assert result.status == ConstraintStatus.PASS


def test_fixed_role_collision_constraint_passes_when_candidate_is_not_forced():
    jungler = _player(1, 1000)
    candidate = _player(2, 1000)
    result = FixedRoleCollisionConstraint().evaluate(
        _partial_context([[jungler]], 0, candidate, {1: RolePreference(main=Position.JUNGLE)}, frozenset({1}))
    )
    assert result.status == ConstraintStatus.PASS
    assert result.prune is False


def test_fixed_role_collision_constraint_prunes_a_second_forced_player_on_the_same_position():
    """Regression test for the bug this plugin fixes: two players both
    hard-forced into JUNGLE used to only get caught by FixedRoleConstraint
    at the leaf, after a complete (doomed) team was already built - with
    enough colliding pairs, that could exhaust the whole search budget
    before finding any satisfying split. This must prune the branch the
    moment the second forced player would join the first's roster."""
    seated = _player(1, 1000)
    candidate = _player(2, 1000)
    preferences = {1: RolePreference(main=Position.JUNGLE), 2: RolePreference(main=Position.JUNGLE)}
    result = FixedRoleCollisionConstraint().evaluate(
        _partial_context([[seated]], 0, candidate, preferences, frozenset({1, 2}))
    )
    assert result.status == ConstraintStatus.FAIL
    assert result.prune is True


def test_fixed_role_collision_constraint_allows_forced_players_on_different_positions():
    seated = _player(1, 1000)
    candidate = _player(2, 1000)
    preferences = {1: RolePreference(main=Position.JUNGLE), 2: RolePreference(main=Position.TOP)}
    result = FixedRoleCollisionConstraint().evaluate(
        _partial_context([[seated]], 0, candidate, preferences, frozenset({1, 2}))
    )
    assert result.status == ConstraintStatus.PASS
    assert result.prune is False


def test_search_engine_rejects_candidates_that_dont_honor_a_fixed_role_override():
    # End-to-end: an overridden player's every returned candidate must
    # actually place them at their forced position - not just prefer it.
    players = [_player(i, 1000 + i * 37, role=Position.MID) for i in range(10)]
    manager = RolePreferenceManager()
    preferences = {p.id: manager.resolve(p) for p in players}
    preferences[players[0].id] = RolePreference(main=Position.SUPPORT)

    engine = BacktrackingSearchEngine(max_nodes=500, time_budget_seconds=3.0)
    results = engine.search_top_k(
        players, preferences, k=3, override_player_ids=frozenset({players[0].id})
    )

    assert len(results) >= 1
    for result in results:
        for team in result.teams:
            for slot in team.slots:
                if slot.player.id == players[0].id:
                    assert slot.position == Position.SUPPORT
                    assert slot.role_source == "main"
