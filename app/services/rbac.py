from __future__ import annotations

from enum import Enum

from app.utils.enums import Role
from app.utils.exceptions import PermissionDeniedError


class Permission(str, Enum):
    """One fine-grained action. Never switch on Role directly in a
    service - check a Permission via has_permission/require_permission so
    a future role only needs an entry in ROLE_PERMISSIONS, not a code
    change at every call site."""

    # Platform-level - reserved for future ops tooling, not enforced by
    # any UI yet (there is no multi-instance deployment to administer).
    VIEW_ALL_SERVERS = "view_all_servers"
    DELETE_ANY_SERVER = "delete_any_server"
    MANAGE_SYSTEM_SETTINGS = "manage_system_settings"

    # Server-level
    MANAGE_SERVER_SETTINGS = "manage_server_settings"
    DELETE_SERVER = "delete_server"
    MANAGE_DISCORD_LINK = "manage_discord_link"
    TRANSFER_OWNERSHIP = "transfer_ownership"
    PROMOTE_TO_SERVER_ADMIN = "promote_to_server_admin"
    REMOVE_SERVER_ADMIN = "remove_server_admin"
    MANAGE_MODERATORS = "manage_moderators"  # reserved, Moderator role unimplemented
    MANAGE_PLAYERS = "manage_players"
    CREATE_MATCH = "create_match"
    SET_SEED_RATING = "set_seed_rating"
    CONFIRM_AI_MVP = "confirm_ai_mvp"
    VIEW_STATISTICS = "view_statistics"

    # Player-level
    LINK_RIOT_ACCOUNT = "link_riot_account"
    VOTE_USER_MVP = "vote_user_mvp"


_PLATFORM_ADMIN_PERMISSIONS = frozenset(
    {
        Permission.VIEW_ALL_SERVERS,
        Permission.DELETE_ANY_SERVER,
        Permission.MANAGE_SYSTEM_SETTINGS,
    }
)

_PLAYER_PERMISSIONS = frozenset(
    {
        Permission.LINK_RIOT_ACCOUNT,
        Permission.VOTE_USER_MVP,
        Permission.VIEW_STATISTICS,
    }
)

_SERVER_ADMIN_PERMISSIONS = _PLAYER_PERMISSIONS | frozenset(
    {
        Permission.MANAGE_PLAYERS,
        Permission.CREATE_MATCH,
        Permission.SET_SEED_RATING,
        Permission.CONFIRM_AI_MVP,
        Permission.PROMOTE_TO_SERVER_ADMIN,
    }
)

_OWNER_PERMISSIONS = _SERVER_ADMIN_PERMISSIONS | frozenset(
    {
        Permission.MANAGE_SERVER_SETTINGS,
        Permission.DELETE_SERVER,
        Permission.MANAGE_DISCORD_LINK,
        Permission.TRANSFER_OWNERSHIP,
        Permission.REMOVE_SERVER_ADMIN,
        Permission.MANAGE_MODERATORS,
    }
)

_MODERATOR_PERMISSIONS: frozenset[Permission] = frozenset()  # reserved, not scoped yet

ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.PLATFORM_ADMIN: _PLATFORM_ADMIN_PERMISSIONS,
    Role.OWNER: _OWNER_PERMISSIONS,
    Role.SERVER_ADMIN: _SERVER_ADMIN_PERMISSIONS,
    Role.MODERATOR: _MODERATOR_PERMISSIONS,
    Role.PLAYER: _PLAYER_PERMISSIONS,
}


def has_permission(role: Role, permission: Permission) -> bool:
    return permission in ROLE_PERMISSIONS.get(role, frozenset())


def require_permission(role: Role, permission: Permission) -> None:
    if not has_permission(role, permission):
        raise PermissionDeniedError(f"{role.value} does not have permission '{permission.value}'")
