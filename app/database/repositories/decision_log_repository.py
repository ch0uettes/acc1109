from __future__ import annotations

from sqlalchemy.orm import Session

from app.database.entities.decision_log import DecisionLogEntity
from app.database.repositories.base import BaseRepository
from app.models.decision_log import (
    DecisionLogEntry,
    PlayerSnapshot,
    RecommendationSnapshot,
    SearchStatisticsSnapshot,
    VersionMetadataSnapshot,
)


def _to_domain(entity: DecisionLogEntity) -> DecisionLogEntry:
    return DecisionLogEntry(
        id=entity.id,
        server_id=entity.server_id,
        execution_id=entity.execution_id,
        created_at=entity.created_at,
        strategy_name=entity.strategy_name,
        search_policy_name=entity.search_policy_name,
        player_ids=list(entity.player_ids),
        player_snapshot=[PlayerSnapshot(**p) for p in entity.player_snapshot] if entity.player_snapshot else [],
        search_statistics=SearchStatisticsSnapshot(**entity.search_statistics) if entity.search_statistics else None,
        version_metadata=VersionMetadataSnapshot(**entity.version_metadata) if entity.version_metadata else None,
        execution_time_seconds=entity.execution_time_seconds,
        candidate_count=entity.candidate_count,
        recommendations=[RecommendationSnapshot(**r) for r in entity.recommendations],
        chosen_rank=entity.chosen_rank,
        chosen_at=entity.chosen_at,
        reason=entity.reason,
    )


class DecisionLogRepository(BaseRepository[DecisionLogEntity]):
    def __init__(self, session: Session, server_id: int) -> None:
        super().__init__(session, DecisionLogEntity)
        self.server_id = server_id

    def add(self, entry: DecisionLogEntry) -> DecisionLogEntry:
        entity = DecisionLogEntity(
            server_id=self.server_id,
            execution_id=entry.execution_id,
            created_at=entry.created_at,
            strategy_name=entry.strategy_name,
            search_policy_name=entry.search_policy_name,
            player_ids=list(entry.player_ids),
            player_snapshot=[p.model_dump() for p in entry.player_snapshot] or None,
            search_statistics=entry.search_statistics.model_dump() if entry.search_statistics else None,
            version_metadata=entry.version_metadata.model_dump() if entry.version_metadata else None,
            execution_time_seconds=entry.execution_time_seconds,
            candidate_count=entry.candidate_count,
            recommendations=[r.model_dump() for r in entry.recommendations],
            chosen_rank=entry.chosen_rank,
            chosen_at=entry.chosen_at,
            reason=entry.reason,
        )
        self.session.add(entity)
        self.session.commit()
        self.session.refresh(entity)
        return _to_domain(entity)

    def list_for_server(self, limit: int = 20) -> list[DecisionLogEntry]:
        # id DESC, not created_at DESC - two entries logged in the same
        # request (or just fast in a test) can share a wall-clock
        # timestamp at this resolution, but id is always strictly
        # insertion-ordered.
        entities = (
            self.session.query(DecisionLogEntity)
            .filter(DecisionLogEntity.server_id == self.server_id)
            .order_by(DecisionLogEntity.id.desc())
            .limit(limit)
            .all()
        )
        return [_to_domain(e) for e in entities]
