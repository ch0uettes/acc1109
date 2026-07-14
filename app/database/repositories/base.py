from __future__ import annotations

from typing import Generic, TypeVar

from sqlalchemy.orm import Session

EntityT = TypeVar("EntityT")


class BaseRepository(Generic[EntityT]):
    def __init__(self, session: Session, entity_cls: type[EntityT]) -> None:
        self.session = session
        self.entity_cls = entity_cls

    def _get_entity(self, entity_id: int) -> EntityT | None:
        return self.session.get(self.entity_cls, entity_id)

    def _list_entities(self) -> list[EntityT]:
        return list(self.session.query(self.entity_cls).all())

    def _delete_entity(self, entity: EntityT) -> None:
        self.session.delete(entity)
        self.session.commit()
