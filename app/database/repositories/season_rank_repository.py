from __future__ import annotations

from sqlalchemy.orm import Session

from app.database.entities.season_rank import PlayerSeasonRankEntity
from app.database.repositories.base import BaseRepository
from app.models.season_rank import PlayerSeasonRank
from app.utils.enums import Division, Tier


def _to_domain(entity: PlayerSeasonRankEntity) -> PlayerSeasonRank:
    return PlayerSeasonRank(
        id=entity.id,
        server_id=entity.server_id,
        player_id=entity.player_id,
        season=entity.season,
        current_tier=Tier(entity.current_tier),
        current_division=Division(entity.current_division),
        current_lp=entity.current_lp,
        peak_tier=Tier(entity.peak_tier) if entity.peak_tier else None,
        peak_division=Division(entity.peak_division) if entity.peak_division else None,
        peak_lp=entity.peak_lp,
        recorded_at=entity.recorded_at,
    )


class SeasonRankRepository(BaseRepository[PlayerSeasonRankEntity]):
    def __init__(self, session: Session, server_id: int) -> None:
        super().__init__(session, PlayerSeasonRankEntity)
        self.server_id = server_id

    def add(self, snapshot: PlayerSeasonRank) -> PlayerSeasonRank:
        entity = PlayerSeasonRankEntity(
            server_id=self.server_id,
            player_id=snapshot.player_id,
            season=snapshot.season,
            current_tier=snapshot.current_tier.value,
            current_division=snapshot.current_division.value,
            current_lp=snapshot.current_lp,
            peak_tier=snapshot.peak_tier.value if snapshot.peak_tier else None,
            peak_division=snapshot.peak_division.value if snapshot.peak_division else None,
            peak_lp=snapshot.peak_lp,
            recorded_at=snapshot.recorded_at,
        )
        self.session.add(entity)
        self.session.commit()
        self.session.refresh(entity)
        return _to_domain(entity)

    def list_for_player(self, player_id: int) -> list[PlayerSeasonRank]:
        entities = (
            self.session.query(PlayerSeasonRankEntity)
            .filter(
                PlayerSeasonRankEntity.server_id == self.server_id,
                PlayerSeasonRankEntity.player_id == player_id,
            )
            .order_by(PlayerSeasonRankEntity.recorded_at)
            .all()
        )
        return [_to_domain(e) for e in entities]
