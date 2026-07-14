from __future__ import annotations

from sqlalchemy.orm import Session

from app.database.entities.seed_rating_change import SeedRatingChangeEntity
from app.database.repositories.base import BaseRepository
from app.models.seed_rating_change import SeedRatingChange


def _to_domain(entity: SeedRatingChangeEntity) -> SeedRatingChange:
    return SeedRatingChange(
        id=entity.id,
        player_id=entity.player_id,
        server_id=entity.server_id,
        old_seed_rating=entity.old_seed_rating,
        new_seed_rating=entity.new_seed_rating,
        changed_by=entity.changed_by,
        changed_at=entity.changed_at,
        reason=entity.reason,
    )


class SeedRatingChangeRepository(BaseRepository[SeedRatingChangeEntity]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, SeedRatingChangeEntity)

    def add(self, change: SeedRatingChange) -> SeedRatingChange:
        entity = SeedRatingChangeEntity(
            player_id=change.player_id,
            server_id=change.server_id,
            old_seed_rating=change.old_seed_rating,
            new_seed_rating=change.new_seed_rating,
            changed_by=change.changed_by,
            changed_at=change.changed_at,
            reason=change.reason,
        )
        self.session.add(entity)
        self.session.commit()
        self.session.refresh(entity)
        return _to_domain(entity)

    def list_for_player(self, player_id: int) -> list[SeedRatingChange]:
        entities = (
            self.session.query(SeedRatingChangeEntity)
            .filter(SeedRatingChangeEntity.player_id == player_id)
            .order_by(SeedRatingChangeEntity.changed_at)
            .all()
        )
        return [_to_domain(e) for e in entities]
