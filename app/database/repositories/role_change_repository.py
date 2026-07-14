from __future__ import annotations

from sqlalchemy.orm import Session

from app.database.entities.role_change import RoleChangeEntity
from app.database.repositories.base import BaseRepository
from app.models.role_change import RoleChange
from app.utils.enums import Role


def _to_domain(entity: RoleChangeEntity) -> RoleChange:
    return RoleChange(
        id=entity.id,
        server_id=entity.server_id,
        membership_id=entity.membership_id,
        target_display_name=entity.target_display_name,
        old_role=Role(entity.old_role) if entity.old_role else None,
        new_role=Role(entity.new_role),
        changed_by=entity.changed_by,
        changed_at=entity.changed_at,
        reason=entity.reason,
    )


class RoleChangeRepository(BaseRepository[RoleChangeEntity]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, RoleChangeEntity)

    def add(self, change: RoleChange) -> RoleChange:
        entity = RoleChangeEntity(
            server_id=change.server_id,
            membership_id=change.membership_id,
            target_display_name=change.target_display_name,
            old_role=change.old_role.value if change.old_role else None,
            new_role=change.new_role.value,
            changed_by=change.changed_by,
            changed_at=change.changed_at,
            reason=change.reason,
        )
        self.session.add(entity)
        self.session.commit()
        self.session.refresh(entity)
        return _to_domain(entity)

    def list_for_server(self, server_id: int) -> list[RoleChange]:
        entities = (
            self.session.query(RoleChangeEntity)
            .filter(RoleChangeEntity.server_id == server_id)
            .order_by(RoleChangeEntity.changed_at)
            .all()
        )
        return [_to_domain(e) for e in entities]
