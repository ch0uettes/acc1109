from __future__ import annotations

from collections import Counter

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.repositories.match_repository import MatchRepository
from app.database.repositories.vote_repository import VoteRepository
from app.models.vote import Vote
from app.services.rbac import Permission, require_permission
from app.utils.enums import Role
from app.utils.exceptions import DuplicateVoteError, InvalidVoteError, MatchNotFoundError


class VoteService:
    def __init__(self, session: Session, server_id: int) -> None:
        self.repo = VoteRepository(session, server_id)
        self.match_repo = MatchRepository(session, server_id)

    def cast_vote(self, match_id: int, voter_player_id: int, voted_player_id: int, actor_role: Role) -> Vote:
        """Every check here runs in the service, not just the UI - a vote
        cast through any future caller (a bot command, a direct API call)
        gets the exact same guarantees.

        Order: permission -> match exists and voting isn't already closed
        -> voter/candidate are actual participants of this match (never
        another match's roster) -> not voting for yourself -> not already
        voted. The uniqueness check is also backed by a DB-level unique
        index (see VoteEntity/migrate_2026_vote_uniqueness.py) - a race
        that slips past the check-then-insert here still can't produce two
        rows, it just surfaces as DuplicateVoteError instead of silently
        succeeding twice."""
        require_permission(actor_role, Permission.VOTE_USER_MVP)

        match = self.match_repo.get(match_id)
        if match is None:
            raise MatchNotFoundError(f"Match {match_id} not found")
        if match.user_mvp_player_id is not None:
            # Guards against a vote landing after an admin already closed
            # voting and confirmed User MVP - without this, a form left
            # open in another tab/session (list_pending_votes only filters
            # at page load) could still insert a vote against a round
            # that's already been tallied and announced.
            raise InvalidVoteError(f"Match {match_id}'s User MVP vote is already closed")

        participant_ids = {p.player_id for p in match.participants}
        if voter_player_id not in participant_ids:
            raise InvalidVoteError(f"Player {voter_player_id} is not a participant of match {match_id}")
        if voted_player_id not in participant_ids:
            raise InvalidVoteError(f"Player {voted_player_id} is not a participant of match {match_id}")
        if voter_player_id == voted_player_id:
            raise InvalidVoteError("자기 자신에게는 투표할 수 없습니다")

        if self.repo.get_existing_vote(match_id, voter_player_id) is not None:
            raise DuplicateVoteError(f"Player {voter_player_id} has already voted for match {match_id}")

        try:
            return self.repo.add(
                Vote(match_id=match_id, voter_player_id=voter_player_id, voted_player_id=voted_player_id)
            )
        except IntegrityError as exc:
            self.repo.session.rollback()
            raise DuplicateVoteError(f"Player {voter_player_id} has already voted for match {match_id}") from exc

    def tally_user_mvp(self, match_id: int) -> int | None:
        votes = self.repo.list_for_match(match_id)
        if not votes:
            return None
        counts = Counter(v.voted_player_id for v in votes)
        return counts.most_common(1)[0][0]
