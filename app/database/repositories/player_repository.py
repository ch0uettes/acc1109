from __future__ import annotations

from sqlalchemy.orm import Session

from app.database.entities.player import PlayerEntity
from app.database.repositories.base import BaseRepository
from app.models.player import Player
from app.utils.enums import Division, Position, RatingSource, Tier
from app.utils.exceptions import PlayerNotFoundError


def _to_domain(entity: PlayerEntity) -> Player:
    return Player(
        id=entity.id,
        server_id=entity.server_id,
        discord_id=entity.discord_id,
        puuid=entity.puuid,
        nickname=entity.nickname,
        tier=Tier(entity.tier),
        division=Division(entity.division),
        lp=entity.lp,
        peak_tier=Tier(entity.peak_tier) if entity.peak_tier else None,
        peak_division=Division(entity.peak_division) if entity.peak_division else None,
        peak_lp=entity.peak_lp,
        official_rating=entity.official_rating,
        seed_rating=entity.seed_rating,
        rating_source=RatingSource(entity.rating_source),
        calibration_mode=entity.calibration_mode,
        internal_rating=entity.internal_rating,
        main_role=Position(entity.main_role),
        sub_role=Position(entity.sub_role) if entity.sub_role else None,
        recommended_main_role=Position(entity.recommended_main_role) if entity.recommended_main_role else None,
        recommended_main_confidence=entity.recommended_main_confidence,
        recommended_sub_role=Position(entity.recommended_sub_role) if entity.recommended_sub_role else None,
        recommended_sub_confidence=entity.recommended_sub_confidence,
        recent_form=entity.recent_form,
        champion_pool=list(entity.champion_pool or []),
        confidence=entity.confidence,
        games_played=entity.games_played,
    )


def _apply_domain(entity: PlayerEntity, player: Player) -> None:
    entity.discord_id = player.discord_id
    entity.puuid = player.puuid
    entity.nickname = player.nickname
    entity.tier = player.tier.value
    entity.division = player.division.value
    entity.lp = player.lp
    entity.peak_tier = player.peak_tier.value if player.peak_tier else None
    entity.peak_division = player.peak_division.value if player.peak_division else None
    entity.peak_lp = player.peak_lp
    entity.official_rating = player.official_rating
    entity.seed_rating = player.seed_rating
    entity.rating_source = player.rating_source.value
    entity.calibration_mode = player.calibration_mode
    entity.internal_rating = player.internal_rating
    entity.main_role = player.main_role.value
    entity.sub_role = player.sub_role.value if player.sub_role else None
    entity.recommended_main_role = player.recommended_main_role.value if player.recommended_main_role else None
    entity.recommended_main_confidence = player.recommended_main_confidence
    entity.recommended_sub_role = player.recommended_sub_role.value if player.recommended_sub_role else None
    entity.recommended_sub_confidence = player.recommended_sub_confidence
    entity.recent_form = player.recent_form
    entity.champion_pool = list(player.champion_pool)
    entity.confidence = player.confidence
    entity.games_played = player.games_played


class PlayerRepository(BaseRepository[PlayerEntity]):
    """Scoped to one Server at construction - every read/write is
    implicitly filtered to it, so a service built for Server A can never
    see or touch Server B's players even by an id typo."""

    def __init__(self, session: Session, server_id: int) -> None:
        super().__init__(session, PlayerEntity)
        self.server_id = server_id

    def add(self, player: Player) -> Player:
        entity = PlayerEntity()
        _apply_domain(entity, player)
        entity.server_id = self.server_id
        self.session.add(entity)
        self.session.commit()
        self.session.refresh(entity)
        return _to_domain(entity)

    def get(self, player_id: int) -> Player:
        entity = self._get_entity(player_id)
        if entity is None or entity.server_id != self.server_id:
            raise PlayerNotFoundError(f"Player {player_id} not found")
        return _to_domain(entity)

    def get_by_nickname(self, nickname: str) -> Player | None:
        entity = (
            self.session.query(PlayerEntity)
            .filter(PlayerEntity.server_id == self.server_id, PlayerEntity.nickname == nickname)
            .one_or_none()
        )
        return _to_domain(entity) if entity else None

    def list(self) -> list[Player]:
        entities = self.session.query(PlayerEntity).filter(PlayerEntity.server_id == self.server_id).all()
        return [_to_domain(e) for e in entities]

    def update(self, player: Player) -> Player:
        if player.id is None:
            raise PlayerNotFoundError("Cannot update a player without an id")
        entity = self._get_entity(player.id)
        if entity is None or entity.server_id != self.server_id:
            raise PlayerNotFoundError(f"Player {player.id} not found")
        _apply_domain(entity, player)
        self.session.commit()
        self.session.refresh(entity)
        return _to_domain(entity)

    def update_internal_rating(
        self, player_id: int, new_internal_rating: float, exit_calibration: bool = False
    ) -> None:
        entity = self._get_entity(player_id)
        if entity is None or entity.server_id != self.server_id:
            raise PlayerNotFoundError(f"Player {player_id} not found")
        entity.internal_rating = new_internal_rating
        entity.games_played += 1
        if exit_calibration:
            entity.calibration_mode = False
        self.session.commit()

    def delete(self, player_id: int) -> None:
        entity = self._get_entity(player_id)
        if entity is None or entity.server_id != self.server_id:
            raise PlayerNotFoundError(f"Player {player_id} not found")
        self._delete_entity(entity)
