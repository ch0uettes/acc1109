from __future__ import annotations

from sqlalchemy.orm import Session

from app.database.entities.match import MatchEntity, MatchPlayerEntity
from app.database.repositories.base import BaseRepository
from app.models.contribution import ContributionScore
from app.models.match import Match, MatchPlayerResult
from app.utils.enums import Position


def _to_domain(entity: MatchEntity) -> Match:
    return Match(
        id=entity.id,
        server_id=entity.server_id,
        played_at=entity.played_at,
        winning_team_index=entity.winning_team_index,
        ai_mvp_player_id=entity.ai_mvp_player_id,
        user_mvp_player_id=entity.user_mvp_player_id,
        note=entity.note,
        participants=[
            MatchPlayerResult(
                player_id=mp.player_id,
                team_index=mp.team_index,
                position=Position(mp.position),
                contribution=ContributionScore(player_id=mp.player_id, combat=mp.contribution_score),
            )
            for mp in entity.match_players
        ],
    )


class MatchRepository(BaseRepository[MatchEntity]):
    def __init__(self, session: Session, server_id: int) -> None:
        super().__init__(session, MatchEntity)
        self.server_id = server_id

    def add(self, match: Match) -> Match:
        entity = MatchEntity(
            server_id=self.server_id,
            played_at=match.played_at,
            winning_team_index=match.winning_team_index,
            ai_mvp_player_id=match.ai_mvp_player_id,
            user_mvp_player_id=match.user_mvp_player_id,
            note=match.note,
        )
        entity.match_players = [
            MatchPlayerEntity(
                player_id=p.player_id,
                team_index=p.team_index,
                position=p.position.value,
                contribution_score=p.contribution.total,
            )
            for p in match.participants
        ]
        self.session.add(entity)
        self.session.commit()
        self.session.refresh(entity)
        return _to_domain(entity)

    def get(self, match_id: int) -> Match | None:
        entity = self._get_entity(match_id)
        if entity is None or entity.server_id != self.server_id:
            return None
        return _to_domain(entity)

    def list(self) -> list[Match]:
        entities = self.session.query(MatchEntity).filter(MatchEntity.server_id == self.server_id).all()
        return [_to_domain(e) for e in entities]

    def list_for_player(self, player_id: int) -> list[Match]:
        return [
            match
            for match in self.list()
            if any(p.player_id == player_id for p in match.participants)
        ]

    def set_user_mvp(self, match_id: int, player_id: int) -> None:
        entity = self._get_entity(match_id)
        if entity is not None and entity.server_id == self.server_id:
            entity.user_mvp_player_id = player_id
            self.session.commit()
