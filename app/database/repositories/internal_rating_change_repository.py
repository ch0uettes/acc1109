from __future__ import annotations

from sqlalchemy.orm import Session

from app.database.entities.internal_rating_change import InternalRatingChangeEntity
from app.database.repositories.base import BaseRepository
from app.models.internal_rating_change import InternalRatingChange


def _to_domain(entity: InternalRatingChangeEntity) -> InternalRatingChange:
    return InternalRatingChange(
        id=entity.id,
        player_id=entity.player_id,
        server_id=entity.server_id,
        old_internal_rating=entity.old_internal_rating,
        new_internal_rating=entity.new_internal_rating,
        changed_by=entity.changed_by,
        changed_at=entity.changed_at,
        reason=entity.reason,
    )


class InternalRatingChangeRepository(BaseRepository[InternalRatingChangeEntity]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, InternalRatingChangeEntity)

    def add(self, change: InternalRatingChange) -> InternalRatingChange:
        entity = InternalRatingChangeEntity(
            player_id=change.player_id,
            server_id=change.server_id,
            old_internal_rating=change.old_internal_rating,
            new_internal_rating=change.new_internal_rating,
            changed_by=change.changed_by,
            changed_at=change.changed_at,
            reason=change.reason,
        )
        self.session.add(entity)
        self.session.commit()
        self.session.refresh(entity)
        return _to_domain(entity)

    def list_for_player(self, player_id: int) -> list[InternalRatingChange]:
        entities = (
            self.session.query(InternalRatingChangeEntity)
            .filter(InternalRatingChangeEntity.player_id == player_id)
            .order_by(InternalRatingChangeEntity.changed_at)
            .all()
        )
        return [_to_domain(e) for e in entities]
