from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.balance.config import HardConstraintConfig, NormalizationConfig
from app.balance.constraint_engine import DEFAULT_CONSTRAINT_REGISTRY
from app.models.role_change import RoleChange
from app.models.server import Server
from app.models.server_membership import ServerMembership
from app.services.server_service import ServerService

router = APIRouter(prefix="/servers", tags=["servers"])


class CreateServerRequest(BaseModel):
    name: str
    owner_display_name: str
    discord_guild_id: Optional[str] = None


class JoinServerRequest(BaseModel):
    display_name: str
    discord_id: Optional[str] = None


class RoleChangeRequest(BaseModel):
    actor_display_name: str
    target_display_name: str
    reason: Optional[str] = None


class SeasonLabelRequest(BaseModel):
    actor_display_name: str
    label: str


class BalanceConfigRequest(BaseModel):
    actor_display_name: str
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
    actor_display_name: str
    priorities: dict[str, int]


@router.get("", response_model=list[Server])
def list_servers(db: Session = Depends(get_db)) -> list[Server]:
    return ServerService(db).list_servers()


@router.post("", response_model=Server)
def create_server(payload: CreateServerRequest, db: Session = Depends(get_db)) -> Server:
    return ServerService(db).create_server(
        payload.name, owner_display_name=payload.owner_display_name, discord_guild_id=payload.discord_guild_id
    )


@router.get("/{server_id}/members", response_model=list[ServerMembership])
def list_members(server_id: int, db: Session = Depends(get_db)) -> list[ServerMembership]:
    return ServerService(db).list_members(server_id)


@router.post("/{server_id}/members", response_model=ServerMembership)
def join_server(server_id: int, payload: JoinServerRequest, db: Session = Depends(get_db)) -> ServerMembership:
    """Self-registration as a base Player - no permission check, matching
    the Streamlit actor picker's "pick a name, no password" model."""
    return ServerService(db).add_player_member(server_id, payload.display_name, payload.discord_id)


@router.post("/{server_id}/members/promote", response_model=ServerMembership)
def promote_member(server_id: int, payload: RoleChangeRequest, db: Session = Depends(get_db)) -> ServerMembership:
    return ServerService(db).promote_to_server_admin(
        server_id, payload.actor_display_name, payload.target_display_name, payload.reason
    )


@router.post("/{server_id}/members/demote", response_model=ServerMembership)
def demote_member(server_id: int, payload: RoleChangeRequest, db: Session = Depends(get_db)) -> ServerMembership:
    return ServerService(db).remove_server_admin(
        server_id, payload.actor_display_name, payload.target_display_name, payload.reason
    )


@router.post("/{server_id}/members/transfer-ownership", response_model=ServerMembership)
def transfer_ownership(server_id: int, payload: RoleChangeRequest, db: Session = Depends(get_db)) -> ServerMembership:
    return ServerService(db).transfer_ownership(
        server_id, payload.actor_display_name, payload.target_display_name, payload.reason
    )


@router.get("/{server_id}/role-changes", response_model=list[RoleChange])
def role_change_history(server_id: int, db: Session = Depends(get_db)) -> list[RoleChange]:
    return ServerService(db).role_change_history(server_id)


@router.put("/{server_id}/season-label", response_model=Server)
def update_season_label(server_id: int, payload: SeasonLabelRequest, db: Session = Depends(get_db)) -> Server:
    return ServerService(db).update_season_label(server_id, payload.actor_display_name, payload.label)


@router.put("/{server_id}/balance-config", response_model=Server)
def update_balance_config(server_id: int, payload: BalanceConfigRequest, db: Session = Depends(get_db)) -> Server:
    return ServerService(db).update_balance_config(
        server_id, payload.actor_display_name, payload.normalization, payload.hard_constraint
    )


@router.get("/{server_id}/constraints", response_model=list[ConstraintInfo])
def list_constraints(server_id: int, db: Session = Depends(get_db)) -> list[ConstraintInfo]:
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
    server_id: int, payload: ConstraintPrioritiesRequest, db: Session = Depends(get_db)
) -> Server:
    return ServerService(db).update_constraint_priorities(server_id, payload.actor_display_name, payload.priorities)
