from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.database.base import Base
from app.models.player import Player
from app.models.team import Team
from app.services.match_service import MatchService
from app.services.player_service import PlayerService
from app.services.team_service import TeamService
from app.services.vote_service import VoteService
from app.utils.enums import Division, Position, Role, Tier
from app.utils.exceptions import DuplicateMatchError, MatchNotFoundError, PermissionDeniedError


@pytest.fixture
def session():
    from app.database import entities  # noqa: F401  registers tables on Base.metadata

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as s:
        yield s


def _teams(player_service: PlayerService) -> list[Team]:
    players = [
        player_service.create_player(
            Player(nickname=f"p{i}", tier=Tier.GOLD, division=Division.I, lp=0, main_role=Position.MID),
            actor_role=Role.SERVER_ADMIN,
        )
        for i in range(10)
    ]
    return [Team(index=0, players=players[:5]), Team(index=1, players=players[5:])]


def _snapshot(player_service: PlayerService, ids: list[int]) -> dict[int, tuple[float, int, bool]]:
    return {
        pid: (p.internal_rating, p.games_played, p.calibration_mode)
        for pid in ids
        for p in [player_service.get_player(pid)]
    }


def _ids(teams: list[Team]) -> list[int]:
    return [p.id for t in teams for p in t.players]


def test_record_keeps_each_players_rating_change(session):
    players, matches = PlayerService(session, 1), MatchService(session, 1)
    teams = _teams(players)
    before = _snapshot(players, _ids(teams))

    match = matches.record_match(teams, winning_team_index=0, actor_role=Role.SERVER_ADMIN)

    assert match.revertible
    for p in match.participants:
        assert p.internal_rating_before == before[p.player_id][0]
        assert p.internal_rating_after == players.get_player(p.player_id).internal_rating
    winners = [p for p in match.participants if p.team_index == 0]
    assert all(p.internal_rating_after > p.internal_rating_before for p in winners)


def test_delete_restores_ratings_games_and_calibration(session):
    players, matches = PlayerService(session, 1), MatchService(session, 1)
    teams = _teams(players)
    calibrating = teams[0].players[0].id
    players.repo.update(players.get_player(calibrating).model_copy(update={"calibration_mode": True, "games_played": 4}))
    before = _snapshot(players, _ids(teams))

    match = matches.record_match(teams, winning_team_index=1, actor_role=Role.SERVER_ADMIN)
    assert players.get_player(calibrating).calibration_mode is False

    assert matches.delete_match(match.id, Role.SERVER_ADMIN) is True
    after = _snapshot(players, _ids(teams))
    for pid in before:
        assert after[pid][0] == pytest.approx(before[pid][0])
        assert after[pid][1] == before[pid][1]
        assert after[pid][2] == before[pid][2]
    assert matches.match_repo.get(match.id) is None


def test_delete_subtracts_only_that_matchs_share(session):
    players, matches = PlayerService(session, 1), MatchService(session, 1)
    teams = _teams(players)
    first = matches.record_match(teams, winning_team_index=0, actor_role=Role.SERVER_ADMIN)
    second = matches.record_match(teams, winning_team_index=1, actor_role=Role.SERVER_ADMIN)
    first_delta = {p.player_id: p.internal_rating_after - p.internal_rating_before for p in first.participants}
    now = _snapshot(players, _ids(teams))

    matches.delete_match(first.id, Role.SERVER_ADMIN)

    for pid, (rating, games, _) in now.items():
        player = players.get_player(pid)
        assert player.internal_rating == pytest.approx(rating - first_delta[pid])
        assert player.games_played == games - 1
    assert matches.match_repo.get(second.id) is not None


def test_legacy_match_is_deleted_without_touching_ratings(session):
    players, matches = PlayerService(session, 1), MatchService(session, 1)
    teams = _teams(players)
    match = matches.record_match(teams, winning_team_index=0, actor_role=Role.SERVER_ADMIN)
    # Simulate a match recorded before rating changes were kept.
    session.execute(text("UPDATE match_players SET internal_rating_before = NULL, internal_rating_after = NULL"))
    session.commit()
    session.expire_all()
    before = _snapshot(players, _ids(teams))

    legacy = matches.match_repo.get(match.id)
    assert legacy.revertible is False
    assert matches.delete_match(match.id, Role.SERVER_ADMIN) is False
    assert _snapshot(players, _ids(teams)) == before
    assert matches.match_repo.get(match.id) is None


def test_delete_also_removes_votes(session):
    players, matches = PlayerService(session, 1), MatchService(session, 1)
    teams = _teams(players)
    match = matches.record_match(teams, winning_team_index=0, actor_role=Role.SERVER_ADMIN)
    voter, voted = teams[0].players[0].id, teams[1].players[0].id
    VoteService(session, 1).cast_vote(match.id, voter, voted, Role.PLAYER)

    matches.delete_match(match.id, Role.SERVER_ADMIN)

    assert session.execute(text("SELECT COUNT(*) FROM votes")).scalar() == 0


def test_delete_requires_permission_and_existing_match(session):
    players, matches = PlayerService(session, 1), MatchService(session, 1)
    match = matches.record_match(_teams(players), winning_team_index=0, actor_role=Role.SERVER_ADMIN)
    with pytest.raises(PermissionDeniedError):
        matches.delete_match(match.id, Role.PLAYER)
    with pytest.raises(MatchNotFoundError):
        matches.delete_match(9999, Role.SERVER_ADMIN)


def test_record_uses_current_ratings_not_the_callers_snapshot(session):
    """Teams are generated (snapshot taken), then a rating changes, then the
    match is recorded: the change must not be overwritten by a rating
    computed from the old snapshot."""
    players, matches = PlayerService(session, 1), MatchService(session, 1)
    teams = _teams(players)
    target = teams[0].players[0].id
    players.override_internal_rating(target, 500.0, Role.SERVER_ADMIN, "운영자", "수동 보정")

    match = matches.record_match(teams, winning_team_index=0, actor_role=Role.SERVER_ADMIN)

    recorded = next(p for p in match.participants if p.player_id == target)
    assert recorded.internal_rating_before == 500.0
    assert players.get_player(target).internal_rating == pytest.approx(recorded.internal_rating_after)
    assert players.get_player(target).internal_rating > 500.0


def test_a_saved_run_can_only_be_recorded_once(session):
    players, matches, team_service = PlayerService(session, 1), MatchService(session, 1), TeamService(session, 1)
    teams = _teams(players)
    team_service.repo.save_generated_teams(teams)
    run_at = team_service.list_saved_runs()[0]

    match = matches.record_match(teams, winning_team_index=0, actor_role=Role.SERVER_ADMIN, team_run_at=run_at)
    assert match.team_run_at == run_at
    with pytest.raises(DuplicateMatchError):
        matches.record_match(teams, winning_team_index=1, actor_role=Role.SERVER_ADMIN, team_run_at=run_at)

    # Deleting the match frees the run to be recorded again (the "fix a
    # wrong winner" path: delete, then record again).
    matches.delete_match(match.id, Role.SERVER_ADMIN)
    again = matches.record_match(teams, winning_team_index=1, actor_role=Role.SERVER_ADMIN, team_run_at=run_at)
    assert again.winning_team_index == 1


def test_list_recent_is_newest_first(session):
    players, matches = PlayerService(session, 1), MatchService(session, 1)
    teams = _teams(players)
    first = matches.record_match(teams, winning_team_index=0, actor_role=Role.SERVER_ADMIN)
    second = matches.record_match(teams, winning_team_index=1, actor_role=Role.SERVER_ADMIN)
    assert [m.id for m in matches.list_recent()] == [second.id, first.id]
