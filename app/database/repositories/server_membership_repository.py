from __future__ import annotations

from sqlalchemy.orm import Session

from app.database.entities.server_membership import ServerMembershipEntity
from app.database.repositories.base import BaseRepository
from app.models.server_membership import ServerMembership
from app.utils.enums import Role


def _to_domain(entity: ServerMembershipEntity) -> ServerMembership:
    return ServerMembership(
        id=entity.id,
        server_id=entity.server_id,
        display_name=entity.display_name,
        discord_id=entity.discord_id,
        role=Role(entity.role),
        created_at=entity.created_at,
    )


class ServerMembershipRepository(BaseRepository[ServerMembershipEntity]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, ServerMembershipEntity)

    def add(self, membership: ServerMembership) -> ServerMembership:
        entity = ServerMembershipEntity(
            server_id=membership.server_id,
            display_name=membership.display_name,
            discord_id=membership.discord_id,
            role=membership.role.value,
        )
        self.session.add(entity)
        self.session.commit()
        self.session.refresh(entity)
        return _to_domain(entity)

    def list_for_server(self, server_id: int) -> list[ServerMembership]:
        entities = (
            self.session.query(ServerMembershipEntity)
            .filter(ServerMembershipEntity.server_id == server_id)
            .order_by(ServerMembershipEntity.created_at)
            .all()
        )
        return [_to_domain(e) for e in entities]

    def get_by_display_name(self, server_id: int, display_name: str) -> ServerMembership | None:
        entity = (
            self.session.query(ServerMembershipEntity)
            .filter(
                ServerMembershipEntity.server_id == server_id,
                ServerMembershipEntity.display_name == display_name,
            )
            .one_or_none()
        )
        return _to_domain(entity) if entity else None

    def update_role(self, membership_id: int, role: Role) -> ServerMembership:
        entity = self._get_entity(membership_id)
        if entity is None:
            raise ValueError(f"ServerMembership {membership_id} not found")
        entity.role = role.value
        self.session.commit()
        self.session.refresh(entity)
        return _to_domain(entity)
