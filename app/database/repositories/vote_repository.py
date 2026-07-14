from __future__ import annotations

from sqlalchemy.orm import Session

from app.database.entities.vote import VoteEntity
from app.database.repositories.base import BaseRepository
from app.models.vote import Vote


def _to_domain(entity: VoteEntity) -> Vote:
    return Vote(
        id=entity.id,
        server_id=entity.server_id,
        match_id=entity.match_id,
        voter_player_id=entity.voter_player_id,
        voted_player_id=entity.voted_player_id,
    )


class VoteRepository(BaseRepository[VoteEntity]):
    def __init__(self, session: Session, server_id: int) -> None:
        super().__init__(session, VoteEntity)
        self.server_id = server_id

    def add(self, vote: Vote) -> Vote:
        entity = VoteEntity(
            server_id=self.server_id,
            match_id=vote.match_id,
            voter_player_id=vote.voter_player_id,
            voted_player_id=vote.voted_player_id,
        )
        self.session.add(entity)
        self.session.commit()
        self.session.refresh(entity)
        return _to_domain(entity)

    def list_for_match(self, match_id: int) -> list[Vote]:
        entities = (
            self.session.query(VoteEntity)
            .filter(VoteEntity.server_id == self.server_id, VoteEntity.match_id == match_id)
            .all()
        )
        return [_to_domain(e) for e in entities]
