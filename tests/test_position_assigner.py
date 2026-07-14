from __future__ import annotations

from app.position.assigner import BipartiteMatchingPositionAssigner
from app.position.schemas import RolePreference
from app.models.player import Player
from app.utils.enums import Position, Tier


def _player(player_id: int, main_role: Position) -> Player:
    return Player(id=player_id, nickname=f"p{player_id}", tier=Tier.GOLD, main_role=main_role)


def test_all_main_available_has_zero_penalty_and_no_other():
    players = [
        _player(1, Position.TOP),
        _player(2, Position.JUNGLE),
        _player(3, Position.MID),
        _player(4, Position.ADC),
        _player(5, Position.SUPPORT),
    ]
    preferences = {p.id: RolePreference(main=p.main_role) for p in players}

    slots = BipartiteMatchingPositionAssigner().assign(players, preferences)

    assert {s.player.id: s.position for s in slots} == {
        1: Position.TOP,
        2: Position.JUNGLE,
        3: Position.MID,
        4: Position.ADC,
        5: Position.SUPPORT,
    }
    assert all(s.role_penalty == 0.0 for s in slots)
    assert all(s.role_source == "main" for s in slots)


def test_conflicting_main_falls_back_to_sub_for_one_player():
    players = [
        _player(1, Position.TOP),
        _player(2, Position.TOP),  # conflicts with p1 - only p2 has a Sub to fall back on
        _player(3, Position.MID),
        _player(4, Position.ADC),
        _player(5, Position.SUPPORT),
    ]
    preferences = {p.id: RolePreference(main=p.main_role) for p in players}
    preferences[2] = RolePreference(main=Position.TOP, sub=Position.JUNGLE)

    slots = BipartiteMatchingPositionAssigner().assign(players, preferences)
    by_player = {s.player.id: s for s in slots}

    assert by_player[1].position == Position.TOP
    assert by_player[1].role_source == "main"
    assert by_player[2].position == Position.JUNGLE
    assert by_player[2].role_source == "sub"
    assert by_player[2].role_penalty == 10.0
    assert sum(s.role_penalty for s in slots) == 10.0
    assert all(s.role_source != "other" for s in slots)


def test_other_used_only_for_the_minimum_necessary_players():
    # All 5 players only ever list TOP (no Sub) - only one of them can
    # actually occupy TOP, so the other 4 have no Main/Sub-valid lane at
    # all and MUST be Other. This is the true worst case, not a
    # gratuitous one - the hard constraint still holds: nobody who has a
    # valid Main/Sub lane available gets bumped to Other.
    players = [_player(i, Position.TOP) for i in range(1, 6)]
    preferences = {p.id: RolePreference(main=Position.TOP) for p in players}

    slots = BipartiteMatchingPositionAssigner().assign(players, preferences)

    main_slots = [s for s in slots if s.role_source == "main"]
    other_slots = [s for s in slots if s.role_source == "other"]
    assert len(main_slots) == 1
    assert main_slots[0].position == Position.TOP
    assert len(other_slots) == 4
    assert not any(s.role_source == "sub" for s in slots)
    # every position still gets filled exactly once
    assert {s.position for s in slots} == set(Position)


def test_assignment_is_deterministic_across_repeated_calls():
    players = [
        _player(1, Position.TOP),
        _player(2, Position.TOP),
        _player(3, Position.JUNGLE),
        _player(4, Position.JUNGLE),
        _player(5, Position.MID),
    ]
    preferences = {p.id: RolePreference(main=p.main_role) for p in players}

    assigner = BipartiteMatchingPositionAssigner()
    first = {s.player.id: (s.position, s.role_penalty) for s in assigner.assign(players, preferences)}
    second = {s.player.id: (s.position, s.role_penalty) for s in assigner.assign(players, preferences)}

    assert first == second
