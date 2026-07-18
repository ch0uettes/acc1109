from __future__ import annotations

from app.balance.search_engine import BacktrackingSearchEngine
from app.models.player import Player
from app.position.preference_manager import RolePreferenceManager
from app.position.schemas import RolePreference
from app.utils.enums import Position, Tier

# Regression coverage for a real production bug: forcing a low-rated
# player into a role several higher-rated players already consider their
# main (via a this-match Fixed Role override) used to make the search
# return a wildly stratified split (one team of the 5 highest-rated
# players, another of the 5 lowest, etc.) instead of a balanced one -
# because FixedRoleConstraint only checked the *result* of
# BipartiteMatchingPositionAssigner's independent cost-minimizing
# assignment, and almost no naturally-explored roster happened to have
# the optimizer land the forced player on the forced role by coincidence.
# The DFS's very first (least-mixed, degenerate) branch was often the
# only one that ever satisfied the constraint, so it became the de facto
# result. See BipartiteMatchingPositionAssigner.assign()'s
# `forced_positions` parameter - the fix pins the role directly during
# assignment instead of leaving it to chance.

ROLE_CYCLE = [Position.TOP, Position.JUNGLE, Position.MID, Position.ADC, Position.SUPPORT]


def _make_players(count: int = 20) -> list[Player]:
    """`count` players, ratings descending from 3000 in even steps, main
    role cycling TOP/JUNGLE/MID/ADC/SUPPORT so every role has an equal
    share of both high- and low-rated players - exactly the setup where a
    naive rating-sorted-into-buckets split is obviously wrong, and where a
    low-rated player forced into a contested role has real competition."""
    players = []
    for i in range(count):
        rating = 3000 - i * 100
        role = ROLE_CYCLE[i % len(ROLE_CYCLE)]
        players.append(Player(id=i + 1, nickname=f"p{i + 1}", tier=Tier.GOLD, main_role=role, official_rating=rating))
    return players


def _team_averages(result) -> list[float]:
    return [sum(p.final_rating for p in team.players) / len(team.players) for team in result.teams]


def _naive_bucket_gap(players: list[Player]) -> float:
    """The exact degenerate outcome the bug used to produce: players
    sorted by rating and chunked into consecutive groups of TEAM_SIZE.
    Used as a normalized upper bound - the real result must do
    meaningfully better than this, not just "not literally identical"."""
    ordered = sorted(players, key=lambda p: p.final_rating, reverse=True)
    team_size = 5
    num_teams = len(players) // team_size
    bucket_averages = []
    for t in range(num_teams):
        bucket = ordered[t * team_size : (t + 1) * team_size]
        bucket_averages.append(sum(p.final_rating for p in bucket) / team_size)
    return max(bucket_averages) - min(bucket_averages)


def test_single_fixed_role_on_a_contested_position_still_balances_teams():
    players = _make_players()
    manager = RolePreferenceManager()
    preferences = {p.id: manager.resolve(p) for p in players}

    # The single lowest-rated player (SUPPORT by role cycle) is forced
    # into JUNGLE for this match - a role 3 other, much higher-rated
    # players already have as their main.
    forced_player = players[-1]
    assert forced_player.main_role == Position.SUPPORT
    preferences[forced_player.id] = RolePreference(main=Position.JUNGLE)

    engine = BacktrackingSearchEngine(max_nodes=20_000, time_budget_seconds=5.0)
    results = engine.search_top_k(
        players, preferences, k=3, override_player_ids=frozenset({forced_player.id})
    )

    assert len(results) >= 1
    naive_gap = _naive_bucket_gap(players)
    for result in results:
        by_player = {slot.player.id: slot for team in result.teams for slot in team.slots}
        assert by_player[forced_player.id].position == Position.JUNGLE
        assert by_player[forced_player.id].role_source == "main"

        gap = max(_team_averages(result)) - min(_team_averages(result))
        assert gap < naive_gap * 0.5, (
            f"team-average gap {gap} isn't meaningfully better than the degenerate "
            f"sorted-bucket gap {naive_gap} - the fixed role may be starving the search again"
        )


def test_two_fixed_roles_on_different_positions_still_balance_teams():
    players = _make_players()
    manager = RolePreferenceManager()
    preferences = {p.id: manager.resolve(p) for p in players}

    # Two low-rated players, each forced into a *different* contested
    # role than their profile main.
    forced_a = players[-1]  # profile main SUPPORT -> forced JUNGLE
    forced_b = players[-2]  # profile main ADC -> forced TOP
    assert forced_a.main_role == Position.SUPPORT
    assert forced_b.main_role == Position.ADC
    preferences[forced_a.id] = RolePreference(main=Position.JUNGLE)
    preferences[forced_b.id] = RolePreference(main=Position.TOP)

    engine = BacktrackingSearchEngine(max_nodes=20_000, time_budget_seconds=5.0)
    results = engine.search_top_k(
        players, preferences, k=3, override_player_ids=frozenset({forced_a.id, forced_b.id})
    )

    assert len(results) >= 1
    naive_gap = _naive_bucket_gap(players)
    for result in results:
        by_player = {slot.player.id: slot for team in result.teams for slot in team.slots}
        assert by_player[forced_a.id].position == Position.JUNGLE
        assert by_player[forced_a.id].role_source == "main"
        assert by_player[forced_b.id].position == Position.TOP
        assert by_player[forced_b.id].role_source == "main"

        gap = max(_team_averages(result)) - min(_team_averages(result))
        assert gap < naive_gap * 0.5


def test_three_fixed_roles_on_different_positions_still_balance_teams():
    players = _make_players()
    manager = RolePreferenceManager()
    preferences = {p.id: manager.resolve(p) for p in players}

    forced_a = players[-1]  # SUPPORT -> JUNGLE
    forced_b = players[-2]  # ADC -> TOP
    forced_c = players[-3]  # MID -> SUPPORT
    preferences[forced_a.id] = RolePreference(main=Position.JUNGLE)
    preferences[forced_b.id] = RolePreference(main=Position.TOP)
    preferences[forced_c.id] = RolePreference(main=Position.SUPPORT)

    engine = BacktrackingSearchEngine(max_nodes=20_000, time_budget_seconds=5.0)
    results = engine.search_top_k(
        players,
        preferences,
        k=3,
        override_player_ids=frozenset({forced_a.id, forced_b.id, forced_c.id}),
    )

    assert len(results) >= 1
    naive_gap = _naive_bucket_gap(players)
    for result in results:
        by_player = {slot.player.id: slot for team in result.teams for slot in team.slots}
        assert by_player[forced_a.id].position == Position.JUNGLE
        assert by_player[forced_a.id].role_source == "main"
        assert by_player[forced_b.id].position == Position.TOP
        assert by_player[forced_b.id].role_source == "main"
        assert by_player[forced_c.id].position == Position.SUPPORT
        assert by_player[forced_c.id].role_source == "main"

        gap = max(_team_averages(result)) - min(_team_averages(result))
        assert gap < naive_gap * 0.5


def test_two_players_forced_to_the_same_position_degrades_gracefully():
    """A genuinely contradictory operator request (two players both
    hard-forced into the same position) can only be satisfied if the
    search happens to keep them on separate teams - it must never crash,
    and whichever roster it returns must still be a complete, valid,
    fully-evaluated result even when the pins can't both be honored on
    the same team."""
    players = _make_players()
    manager = RolePreferenceManager()
    preferences = {p.id: manager.resolve(p) for p in players}

    forced_a = players[-1]
    forced_b = players[-2]
    preferences[forced_a.id] = RolePreference(main=Position.JUNGLE)
    preferences[forced_b.id] = RolePreference(main=Position.JUNGLE)

    engine = BacktrackingSearchEngine(max_nodes=20_000, time_budget_seconds=5.0)
    results = engine.search_top_k(
        players, preferences, k=3, override_player_ids=frozenset({forced_a.id, forced_b.id})
    )

    assert len(results) >= 1
    for result in results:
        for team in result.teams:
            assert len(team.players) == 5
            assert {slot.position for slot in team.slots} == set(Position)
