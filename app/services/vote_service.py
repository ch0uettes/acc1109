from __future__ import annotations

from collections import Counter

from sqlalchemy.orm import Session

from app.database.repositories.vote_repository import VoteRepository
from app.models.vote import Vote


class VoteService:
    def __init__(self, session: Session, server_id: int) -> None:
        self.repo = VoteRepository(session, server_id)

    def cast_vote(self, match_id: int, voter_player_id: int, voted_player_id: int) -> Vote:
        return self.repo.add(
            Vote(match_id=match_id, voter_player_id=voter_player_id, voted_player_id=voted_player_id)
        )

    def tally_user_mvp(self, match_id: int) -> int | None:
        votes = self.repo.list_for_match(match_id)
        if not votes:
            return None
        counts = Counter(v.voted_player_id for v in votes)
        return counts.most_common(1)[0][0]
