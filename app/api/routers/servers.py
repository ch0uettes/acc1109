from __future__ import annotations

import hmac
import os
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_actor, get_db
from app.auth import issue_token
from app.config import settings
from app.balance.config import HardConstraintConfig, NormalizationConfig
from app.balance.constraint_engine import DEFAULT_CONSTRAINT_REGISTRY
from app.models.role_change import RoleChange
from app.models.server import Server
from app.models.server_membership import ServerMembership
from app.services.rbac import Permission, require_permission
from app.services.server_service import ServerService
from app.utils.exceptions import PermissionDeniedError

router = APIRouter(prefix="/servers", tags=["servers"])


class CreateServerRequest(BaseModel):
    name: str
    owner_display_name: str
    join_code: str
    owner_pin: str
    # Must match SERVER_CREATION_CODE when that env var is set.
    creation_code: Optional[str] = None
    discord_guild_id: Optional[str] = None


class LoginRequest(BaseModel):
    display_name: str
    join_code: str = ""
    # Only checked for Owner/Server Admin - ignored for a Player.
    pin: Optional[str] = None


class SessionResponse(BaseModel):
    token: str
    member: ServerMembership


class JoinCodeRequest(BaseModel):
    join_code: str


class ResetPinRequest(BaseModel):
    target_display_name: str


class RenameServerRequest(BaseModel):
    name: str


class RenameMemberRequest(BaseModel):
    target_display_name: str
    new_display_name: str


class RiotApiKeyRequest(BaseModel):
    api_key: str


class RiotApiKeyStatus(BaseModel):
    configured: bool
    source: Optional[str] = None  # "db" | "env" | None
    last4: Optional[str] = None


class ChangePinRequest(BaseModel):
    current_pin: str
    new_pin: str


class RoleChangeRequest(BaseModel):
    target_display_name: str
    reason: Optional[str] = None


class SeasonLabelRequest(BaseModel):
    label: str


class BalanceConfigRequest(BaseModel):
    normalization: NormalizationConfig
    hard_constraint: HardConstraintConfig


class ConstraintInfo(BaseModel):
    name: str
    description: str
    tier: str
    pipeline: str
    default_priority: int
    current_priority: int


class ConstraintPrioritiesRequest(BaseModel):
    priorities: dict[str, int]


@router.get("", response_model=list[Server])
def list_servers(db: Session = Depends(get_db)) -> list[Server]:
    return ServerService(db).list_servers()


def _session_response(service: ServerService, member: ServerMembership) -> SessionResponse:
    return SessionResponse(token=issue_token(service.claims_for(member)), member=member)


def _check_creation_code(creation_code: Optional[str]) -> None:
    expected = settings.server_creation_code
    if expected is None:
        if os.environ.get("VERCEL"):
            raise PermissionDeniedError("서버 생성이 비활성화되어 있습니다 (SERVER_CREATION_CODE 미설정)")
        return
    if not hmac.compare_digest((creation_code or "").strip(), expected):
        raise PermissionDeniedError("서버 생성 코드가 올바르지 않습니다")


@router.post("", response_model=SessionResponse)
def create_server(payload: CreateServerRequest, db: Session = Depends(get_db)) -> SessionResponse:
    _check_creation_code(payload.creation_code)
    service = ServerService(db)
    server = service.create_server(
        payload.name,
        owner_display_name=payload.owner_display_name,
        discord_guild_id=payload.discord_guild_id,
        join_code=payload.join_code,
        owner_pin=payload.owner_pin,
    )
    return _session_response(service, service.get_member(server.id, payload.owner_display_name))


@router.post("/{server_id}/session", response_model=SessionResponse)
def login(server_id: int, payload: LoginRequest, db: Session = Depends(get_db)) -> SessionResponse:
    """Entry code for everyone, plus PIN for Owner/Server Admin - see
    ServerService.authenticate. A new name self-registers as a Player."""
    service = ServerService(db)
    member, claims = service.authenticate(server_id, payload.display_name, payload.join_code, payload.pin)
    return SessionResponse(token=issue_token(claims), member=member)


@router.get("/{server_id}/me", response_model=ServerMembership)
def me(actor: ServerMembership = Depends(get_actor)) -> ServerMembership:
    return actor


@router.put("/{server_id}/me/pin", response_model=SessionResponse)
def change_own_pin(
    payload: ChangePinRequest, db: Session = Depends(get_db), actor: ServerMembership = Depends(get_actor)
) -> SessionResponse:
    """Re-issues the caller's token - the old one is pinned to the old PIN."""
    service = ServerService(db)
    return _session_response(service, service.change_own_pin(actor, payload.current_pin, payload.new_pin))


@router.put("/{server_id}/join-code", response_model=SessionResponse)
def set_join_code(
    server_id: int,
    payload: JoinCodeRequest,
    db: Session = Depends(get_db),
    actor: ServerMembership = Depends(get_actor),
) -> SessionResponse:
    """Logs every member out (tokens are pinned to the old code) - the
    Owner gets a fresh token back so their own session survives."""
    service = ServerService(db)
    service.set_join_code(server_id, actor.display_name, payload.join_code)
    return _session_response(service, actor)


@router.put("/{server_id}/name", response_model=Server)
def rename_server(
    server_id: int,
    payload: RenameServerRequest,
    db: Session = Depends(get_db),
    actor: ServerMembership = Depends(get_actor),
) -> Server:
    return ServerService(db).rename_server(server_id, actor.display_name, payload.name)


@router.put("/{server_id}/members/rename", response_model=ServerMembership)
def rename_member(
    server_id: int,
    payload: RenameMemberRequest,
    db: Session = Depends(get_db),
    actor: ServerMembership = Depends(get_actor),
) -> ServerMembership:
    return ServerService(db).rename_member(
        server_id, actor.display_name, payload.target_display_name, payload.new_display_name
    )


@router.get("/{server_id}/riot-api-key", response_model=RiotApiKeyStatus)
def riot_api_key_status(
    db: Session = Depends(get_db), actor: ServerMembership = Depends(get_actor)
) -> RiotApiKeyStatus:
    require_permission(actor.role, Permission.MANAGE_SERVER_SETTINGS)
    return RiotApiKeyStatus(**ServerService(db).riot_api_key_status())


class RiotApiKeyCheck(BaseModel):
    valid: bool
    detail: str


@router.post("/{server_id}/riot-api-key/check", response_model=RiotApiKeyCheck)
def check_riot_api_key(
    server_id: int, db: Session = Depends(get_db), actor: ServerMembership = Depends(get_actor)
) -> RiotApiKeyCheck:
    return RiotApiKeyCheck(**ServerService(db).check_riot_api_key(server_id, actor.display_name))


@router.put("/{server_id}/riot-api-key", response_model=RiotApiKeyStatus)
def set_riot_api_key(
    server_id: int,
    payload: RiotApiKeyRequest,
    db: Session = Depends(get_db),
    actor: ServerMembership = Depends(get_actor),
) -> RiotApiKeyStatus:
    return RiotApiKeyStatus(**ServerService(db).set_riot_api_key(server_id, actor.display_name, payload.api_key))


@router.get("/{server_id}/members", response_model=list[ServerMembership])
def list_members(
    server_id: int, db: Session = Depends(get_db), actor: ServerMembership = Depends(get_actor)
) -> list[ServerMembership]:
    return ServerService(db).list_members(server_id)


@router.post("/{server_id}/members/reset-pin", response_model=ServerMembership)
def reset_member_pin(
    server_id: int,
    payload: ResetPinRequest,
    db: Session = Depends(get_db),
    actor: ServerMembership = Depends(get_actor),
) -> ServerMembership:
    return ServerService(db).reset_member_pin(server_id, actor.display_name, payload.target_display_name)


@router.post("/{server_id}/members/promote", response_model=ServerMembership)
def promote_member(
    server_id: int,
    payload: RoleChangeRequest,
    db: Session = Depends(get_db),
    actor: ServerMembership = Depends(get_actor),
) -> ServerMembership:
    return ServerService(db).promote_to_server_admin(
        server_id, actor.display_name, payload.target_display_name, payload.reason
    )


@router.post("/{server_id}/members/demote", response_model=ServerMembership)
def demote_member(
    server_id: int,
    payload: RoleChangeRequest,
    db: Session = Depends(get_db),
    actor: ServerMembership = Depends(get_actor),
) -> ServerMembership:
    return ServerService(db).remove_server_admin(
        server_id, actor.display_name, payload.target_display_name, payload.reason
    )


@router.post("/{server_id}/members/transfer-ownership", response_model=ServerMembership)
def transfer_ownership(
    server_id: int,
    payload: RoleChangeRequest,
    db: Session = Depends(get_db),
    actor: ServerMembership = Depends(get_actor),
) -> ServerMembership:
    return ServerService(db).transfer_ownership(
        server_id, actor.display_name, payload.target_display_name, payload.reason
    )


@router.get("/{server_id}/role-changes", response_model=list[RoleChange])
def role_change_history(
    server_id: int, db: Session = Depends(get_db), actor: ServerMembership = Depends(get_actor)
) -> list[RoleChange]:
    return ServerService(db).role_change_history(server_id)


@router.put("/{server_id}/season-label", response_model=Server)
def update_season_label(
    server_id: int,
    payload: SeasonLabelRequest,
    db: Session = Depends(get_db),
    actor: ServerMembership = Depends(get_actor),
) -> Server:
    return ServerService(db).update_season_label(server_id, actor.display_name, payload.label)


@router.put("/{server_id}/balance-config", response_model=Server)
def update_balance_config(
    server_id: int,
    payload: BalanceConfigRequest,
    db: Session = Depends(get_db),
    actor: ServerMembership = Depends(get_actor),
) -> Server:
    return ServerService(db).update_balance_config(
        server_id, actor.display_name, payload.normalization, payload.hard_constraint
    )


@router.get("/{server_id}/constraints", response_model=list[ConstraintInfo])
def list_constraints(
    server_id: int, db: Session = Depends(get_db), actor: ServerMembership = Depends(get_actor)
) -> list[ConstraintInfo]:
    server = ServerService(db).get_server(server_id)
    overrides = server.constraint_priorities if server else {}
    infos = []
    for name in DEFAULT_CONSTRAINT_REGISTRY.names():
        cls = DEFAULT_CONSTRAINT_REGISTRY.get(name)
        infos.append(
            ConstraintInfo(
                name=name,
                description=cls.description,
                tier=cls.tier.value,
                pipeline=cls.pipeline.value,
                default_priority=cls.default_priority,
                current_priority=overrides.get(name, cls.default_priority),
            )
        )
    return infos


@router.put("/{server_id}/constraint-priorities", response_model=Server)
def update_constraint_priorities(
    server_id: int,
    payload: ConstraintPrioritiesRequest,
    db: Session = Depends(get_db),
    actor: ServerMembership = Depends(get_actor),
) -> Server:
    return ServerService(db).update_constraint_priorities(server_id, actor.display_name, payload.priorities)
