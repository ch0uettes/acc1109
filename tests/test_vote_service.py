from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.base import Base
from app.models.player import Player
from app.models.team import Team
from app.services.match_service import MatchService
from app.services.player_service import PlayerService
from app.services.vote_service import VoteService
from app.utils.enums import Division, Position, Role, Tier
from app.utils.exceptions import DuplicateVoteError, InvalidVoteError, MatchNotFoundError, PermissionDeniedError


@pytest.fixture
def session():
    from app.database import entities  # noqa: F401  registers tables on Base.metadata

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    with SessionLocal() as s:
        yield s


def _make_full_teams(player_service: PlayerService, prefix: str = "p") -> list[Team]:
    players = []
    for i in range(10):
        p = player_service.create_player(
            Player(nickname=f"{prefix}{i}", tier=Tier.GOLD, division=Division.I, lp=0, main_role=Position.MID),
            actor_role=Role.SERVER_ADMIN,
        )
        players.append(p)
    return [Team(index=0, players=players[:5]), Team(index=1, players=players[5:])]


def _make_match(session, prefix: str = "p"):
    player_service = PlayerService(session, server_id=1)
    teams = _make_full_teams(player_service, prefix=prefix)
    match_service = MatchService(session, server_id=1)
    match = match_service.record_match(teams, winning_team_index=0, actor_role=Role.SERVER_ADMIN)
    participant_ids = [p.player_id for p in match.participants]
    return match, participant_ids


def test_a_participant_can_vote_for_another_participant(session):
    match, participant_ids = _make_match(session)
    vote_service = VoteService(session, server_id=1)

    vote = vote_service.cast_vote(
        match_id=match.id,
        voter_player_id=participant_ids[0],
        voted_player_id=participant_ids[1],
        actor_role=Role.PLAYER,
    )

    assert vote.voter_player_id == participant_ids[0]
    assert vote.voted_player_id == participant_ids[1]


def test_a_role_without_vote_permission_is_rejected(session):
    match, participant_ids = _make_match(session)
    vote_service = VoteService(session, server_id=1)

    with pytest.raises(PermissionDeniedError):
        vote_service.cast_vote(
            match_id=match.id,
            voter_player_id=participant_ids[0],
            voted_player_id=participant_ids[1],
            actor_role=Role.MODERATOR,
        )


def test_a_non_participant_voter_is_rejected(session):
    match, participant_ids = _make_match(session)
    vote_service = VoteService(session, server_id=1)
    outsider_id = max(participant_ids) + 1000

    with pytest.raises(InvalidVoteError):
        vote_service.cast_vote(
            match_id=match.id,
            voter_player_id=outsider_id,
            voted_player_id=participant_ids[0],
            actor_role=Role.PLAYER,
        )


def test_voting_for_a_non_participant_candidate_is_rejected(session):
    match, participant_ids = _make_match(session)
    vote_service = VoteService(session, server_id=1)
    outsider_id = max(participant_ids) + 1000

    with pytest.raises(InvalidVoteError):
        vote_service.cast_vote(
            match_id=match.id,
            voter_player_id=participant_ids[0],
            voted_player_id=outsider_id,
            actor_role=Role.PLAYER,
        )


def test_a_participant_from_a_different_match_cannot_vote(session):
    match_a, participants_a = _make_match(session, prefix="a")
    match_b, participants_b = _make_match(session, prefix="b")
    vote_service = VoteService(session, server_id=1)

    with pytest.raises(InvalidVoteError):
        vote_service.cast_vote(
            match_id=match_b.id,
            voter_player_id=participants_a[0],
            voted_player_id=participants_b[0],
            actor_role=Role.PLAYER,
        )


def test_the_same_voter_cannot_vote_twice_for_the_same_match(session):
    match, participant_ids = _make_match(session)
    vote_service = VoteService(session, server_id=1)

    vote_service.cast_vote(
        match_id=match.id,
        voter_player_id=participant_ids[0],
        voted_player_id=participant_ids[1],
        actor_role=Role.PLAYER,
    )

    with pytest.raises(DuplicateVoteError):
        vote_service.cast_vote(
            match_id=match.id,
            voter_player_id=participant_ids[0],
            voted_player_id=participant_ids[2],
            actor_role=Role.PLAYER,
        )


def test_a_db_level_race_past_the_precheck_still_surfaces_as_duplicate_vote_error(session, monkeypatch):
    """Defense-in-depth: even if get_existing_vote() misses a genuine race
    (two requests both check before either inserts), the unique index on
    (match_id, voter_player_id) still stops a second row, and the service
    must translate that raw IntegrityError into DuplicateVoteError - not
    crash, and not leave the session's transaction broken for later calls."""
    match, participant_ids = _make_match(session)
    vote_service = VoteService(session, server_id=1)

    vote_service.cast_vote(
        match_id=match.id,
        voter_player_id=participant_ids[0],
        voted_player_id=participant_ids[1],
        actor_role=Role.PLAYER,
    )

    # Simulate the precheck losing a race: it reports "no existing vote"
    # even though one was just committed, so the only thing left to catch
    # the duplicate is the DB's own unique index.
    monkeypatch.setattr(vote_service.repo, "get_existing_vote", lambda match_id, voter_player_id: None)

    with pytest.raises(DuplicateVoteError):
        vote_service.cast_vote(
            match_id=match.id,
            voter_player_id=participant_ids[0],
            voted_player_id=participant_ids[2],
            actor_role=Role.PLAYER,
        )

    # the session must still be usable afterwards (rollback happened)
    tally = vote_service.tally_user_mvp(match.id)
    assert tally == participant_ids[1]


def test_voting_for_a_nonexistent_match_is_rejected(session):
    vote_service = VoteService(session, server_id=1)

    with pytest.raises(MatchNotFoundError):
        vote_service.cast_vote(match_id=999, voter_player_id=1, voted_player_id=2, actor_role=Role.PLAYER)


def test_a_participant_cannot_vote_for_themselves(session):
    match, participant_ids = _make_match(session)
    vote_service = VoteService(session, server_id=1)

    with pytest.raises(InvalidVoteError):
        vote_service.cast_vote(
            match_id=match.id,
            voter_player_id=participant_ids[0],
            voted_player_id=participant_ids[0],
            actor_role=Role.PLAYER,
        )


def test_voting_is_rejected_once_user_mvp_is_already_confirmed(session):
    """Regression test: list_pending_votes() only filters closed matches
    out of the dropdown at page load - a form left open in another tab, or
    a request that arrives right after an admin confirms User MVP, could
    otherwise still insert a vote against a round that's already been
    tallied and announced."""
    match, participant_ids = _make_match(session)
    vote_service = VoteService(session, server_id=1)
    match_service = MatchService(session, server_id=1)

    vote_service.cast_vote(
        match_id=match.id,
        voter_player_id=participant_ids[0],
        voted_player_id=participant_ids[1],
        actor_role=Role.PLAYER,
    )
    match_service.set_user_mvp(match.id, participant_ids[1], actor_role=Role.SERVER_ADMIN)

    with pytest.raises(InvalidVoteError):
        vote_service.cast_vote(
            match_id=match.id,
            voter_player_id=participant_ids[2],
            voted_player_id=participant_ids[1],
            actor_role=Role.PLAYER,
        )
