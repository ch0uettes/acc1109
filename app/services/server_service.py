from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.balance.config import HardConstraintConfig, NormalizationConfig
from app.database.repositories.role_change_repository import RoleChangeRepository
from app.database.repositories.server_membership_repository import ServerMembershipRepository
from app.database.repositories.server_repository import ServerRepository
from app.models.role_change import RoleChange
from app.models.server import Server
from app.models.server_membership import ServerMembership
from app.services.rbac import Permission, require_permission
from app.utils.enums import Role
from app.utils.exceptions import AppError


class MembershipNotFoundError(AppError):
    pass


class ServerService:
    """Not server-scoped itself (it's what lets you create/pick a server in
    the first place), unlike every other *Service in this project. Also
    owns the RBAC surface: every Role change (promote/demote/ownership
    transfer, including the very first Owner grant at creation) goes
    through here and is always audited via RoleChangeRepository."""

    def __init__(self, session: Session) -> None:
        self.server_repo = ServerRepository(session)
        self.membership_repo = ServerMembershipRepository(session)
        self.role_change_repo = RoleChangeRepository(session)

    def create_server(self, name: str, owner_display_name: str, discord_guild_id: str | None = None) -> Server:
        """The user who creates a Server automatically becomes its Owner -
        every Server has exactly one at all times."""
        server = self.server_repo.add(Server(name=name, discord_guild_id=discord_guild_id, created_at=datetime.utcnow()))
        owner = self.membership_repo.add(
            ServerMembership(
                server_id=server.id,
                display_name=owner_display_name,
                role=Role.OWNER,
                created_at=datetime.utcnow(),
            )
        )
        self._log_role_change(server.id, owner, old_role=None, new_role=Role.OWNER, changed_by=owner_display_name, reason="서버 생성")
        return server

    def list_servers(self) -> list[Server]:
        return self.server_repo.list()

    def get_server(self, server_id: int) -> Server | None:
        return self.server_repo.get(server_id)

    def list_members(self, server_id: int) -> list[ServerMembership]:
        return self.membership_repo.list_for_server(server_id)

    def get_member(self, server_id: int, display_name: str) -> ServerMembership | None:
        return self.membership_repo.get_by_display_name(server_id, display_name)

    def add_player_member(self, server_id: int, display_name: str, discord_id: str | None = None) -> ServerMembership:
        """Self-registration as a base Player - every identity gets this
        much access with no permission check, matching the Player role's
        baseline (link Riot account, join matches, vote, view stats)."""
        existing = self.get_member(server_id, display_name)
        if existing is not None:
            return existing
        return self.membership_repo.add(
            ServerMembership(
                server_id=server_id,
                display_name=display_name,
                discord_id=discord_id,
                role=Role.PLAYER,
                created_at=datetime.utcnow(),
            )
        )

    def promote_to_server_admin(
        self, server_id: int, actor_display_name: str, target_display_name: str, reason: str | None = None
    ) -> ServerMembership:
        """Owner and Server Admin can both do this."""
        actor = self._require_member(server_id, actor_display_name)
        require_permission(actor.role, Permission.PROMOTE_TO_SERVER_ADMIN)

        target = self.add_player_member(server_id, target_display_name)
        return self._change_role(server_id, target, Role.SERVER_ADMIN, actor_display_name, reason)

    def remove_server_admin(
        self, server_id: int, actor_display_name: str, target_display_name: str, reason: str | None = None
    ) -> ServerMembership:
        """Owner only - demotes a Server Admin back to Player."""
        actor = self._require_member(server_id, actor_display_name)
        require_permission(actor.role, Permission.REMOVE_SERVER_ADMIN)

        target = self._require_member(server_id, target_display_name)
        return self._change_role(server_id, target, Role.PLAYER, actor_display_name, reason)

    def transfer_ownership(
        self, server_id: int, actor_display_name: str, new_owner_display_name: str, reason: str | None = None
    ) -> ServerMembership:
        """Only the current Owner can do this. The outgoing Owner becomes a
        Server Admin rather than a plain Player, since they were trusted
        with full server operation a moment ago."""
        actor = self._require_member(server_id, actor_display_name)
        require_permission(actor.role, Permission.TRANSFER_OWNERSHIP)

        new_owner = self.add_player_member(server_id, new_owner_display_name)
        promoted = self._change_role(server_id, new_owner, Role.OWNER, actor_display_name, reason)
        self._change_role(server_id, actor, Role.SERVER_ADMIN, actor_display_name, reason or "Owner 이전")
        return promoted

    def role_change_history(self, server_id: int) -> list[RoleChange]:
        return self.role_change_repo.list_for_server(server_id)

    def update_balance_config(
        self,
        server_id: int,
        actor_display_name: str,
        normalization: NormalizationConfig,
        hard_constraint: HardConstraintConfig,
    ) -> Server:
        """Owner only - overrides this Server's Feature Normalizer /
        Hard Constraint thresholds (app/balance/config.py) for every
        future team generation on this server. NULL/default fields fall
        back to DEFAULT_NORMALIZATION_CONFIG/DEFAULT_HARD_CONSTRAINT_CONFIG
        automatically (see ServerRepository)."""
        actor = self._require_member(server_id, actor_display_name)
        require_permission(actor.role, Permission.MANAGE_SERVER_SETTINGS)
        return self.server_repo.update_balance_config(server_id, normalization, hard_constraint)

    def update_season_label(self, server_id: int, actor_display_name: str, label: str) -> Server:
        """Owner/Server Admin only - overrides this Server's current
        season label (stamped onto future PlayerSeasonRank snapshots,
        never a scoring input). Same permission tier as
        update_balance_config since both are server-wide settings edited
        on the same 서버 관리 page."""
        actor = self._require_member(server_id, actor_display_name)
        require_permission(actor.role, Permission.MANAGE_SERVER_SETTINGS)
        return self.server_repo.update_season_label(server_id, label)

    def _change_role(
        self, server_id: int, target: ServerMembership, new_role: Role, changed_by: str, reason: str | None
    ) -> ServerMembership:
        old_role = target.role
        updated = self.membership_repo.update_role(target.id, new_role)
        self._log_role_change(server_id, updated, old_role=old_role, new_role=new_role, changed_by=changed_by, reason=reason)
        return updated

    def _log_role_change(
        self,
        server_id: int,
        target: ServerMembership,
        old_role: Role | None,
        new_role: Role,
        changed_by: str,
        reason: str | None,
    ) -> None:
        self.role_change_repo.add(
            RoleChange(
                server_id=server_id,
                membership_id=target.id,
                target_display_name=target.display_name,
                old_role=old_role,
                new_role=new_role,
                changed_by=changed_by,
                changed_at=datetime.utcnow(),
                reason=reason,
            )
        )

    def _require_member(self, server_id: int, display_name: str) -> ServerMembership:
        member = self.get_member(server_id, display_name)
        if member is None:
            raise MembershipNotFoundError(f"{display_name} is not a member of server {server_id}")
        return member
