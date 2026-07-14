from __future__ import annotations

import dataclasses

from sqlalchemy.orm import Session

from app.balance.config import (
    DEFAULT_HARD_CONSTRAINT_CONFIG,
    DEFAULT_NORMALIZATION_CONFIG,
    HardConstraintConfig,
    NormalizationConfig,
)
from app.database.entities.server import ServerEntity
from app.database.repositories.base import BaseRepository
from app.models.server import Server


def _normalization_config_from_json(data: dict | None) -> NormalizationConfig:
    if data is None:
        return DEFAULT_NORMALIZATION_CONFIG
    data = dict(data)
    data["tier_distribution_breakpoints"] = tuple(
        tuple(point) for point in data["tier_distribution_breakpoints"]
    )
    return NormalizationConfig(**data)


def _hard_constraint_config_from_json(data: dict | None) -> HardConstraintConfig:
    if data is None:
        return DEFAULT_HARD_CONSTRAINT_CONFIG
    return HardConstraintConfig(**data)


def _to_domain(entity: ServerEntity) -> Server:
    return Server(
        id=entity.id,
        name=entity.name,
        discord_guild_id=entity.discord_guild_id,
        created_at=entity.created_at,
        normalization_config=_normalization_config_from_json(entity.normalization_config),
        hard_constraint_config=_hard_constraint_config_from_json(entity.hard_constraint_config),
    )


class ServerRepository(BaseRepository[ServerEntity]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, ServerEntity)

    def add(self, server: Server) -> Server:
        entity = ServerEntity(name=server.name, discord_guild_id=server.discord_guild_id)
        self.session.add(entity)
        self.session.commit()
        self.session.refresh(entity)
        return _to_domain(entity)

    def get(self, server_id: int) -> Server | None:
        entity = self._get_entity(server_id)
        return _to_domain(entity) if entity else None

    def list(self) -> list[Server]:
        return [_to_domain(e) for e in self._list_entities()]

    def update_balance_config(
        self, server_id: int, normalization: NormalizationConfig, hard_constraint: HardConstraintConfig
    ) -> Server:
        entity = self._get_entity(server_id)
        entity.normalization_config = dataclasses.asdict(normalization)
        entity.hard_constraint_config = dataclasses.asdict(hard_constraint)
        self.session.commit()
        self.session.refresh(entity)
        return _to_domain(entity)
