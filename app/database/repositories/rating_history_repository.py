from __future__ import annotations

from sqlalchemy.orm import Session

from app.database.entities.rating_history import RatingHistoryEntity
from app.database.repositories.base import BaseRepository
from app.models.rating_history import RatingHistory


def _to_domain(entity: RatingHistoryEntity) -> RatingHistory:
    return RatingHistory(
        id=entity.id,
        server_id=entity.server_id,
        player_id=entity.player_id,
        recorded_at=entity.recorded_at,
        official_rating=entity.official_rating,
        internal_rating=entity.internal_rating,
        reason=entity.reason,
    )


class RatingHistoryRepository(BaseRepository[RatingHistoryEntity]):
    def __init__(self, session: Session, server_id: int) -> None:
        super().__init__(session, RatingHistoryEntity)
        self.server_id = server_id

    def add(self, history: RatingHistory) -> RatingHistory:
        entity = RatingHistoryEntity(
            server_id=self.server_id,
            player_id=history.player_id,
            recorded_at=history.recorded_at,
            official_rating=history.official_rating,
            internal_rating=history.internal_rating,
            reason=history.reason,
        )
        self.session.add(entity)
        self.session.commit()
        self.session.refresh(entity)
        return _to_domain(entity)

    def list_for_player(self, player_id: int) -> list[RatingHistory]:
        entities = (
            self.session.query(RatingHistoryEntity)
            .filter(RatingHistoryEntity.server_id == self.server_id, RatingHistoryEntity.player_id == player_id)
            .order_by(RatingHistoryEntity.recorded_at)
            .all()
        )
        return [_to_domain(e) for e in entities]
