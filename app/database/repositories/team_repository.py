from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.database.entities.team import TeamEntity, TeamPlayerEntity
from app.database.repositories.base import BaseRepository
from app.models.team import Team


class TeamRepository(BaseRepository[TeamEntity]):
    def __init__(self, session: Session, server_id: int) -> None:
        super().__init__(session, TeamEntity)
        self.server_id = server_id

    def save_generated_teams(self, teams: list[Team]) -> list[int]:
        """Persists one balancer run. All rows share `generated_at` so a
        later query can group them back into one run without a batch table."""
        generated_at = datetime.utcnow()
        saved_ids: list[int] = []
        for team in teams:
            entity = TeamEntity(server_id=self.server_id, team_index=team.index, generated_at=generated_at)
            entity.team_players = [
                TeamPlayerEntity(player_id=player.id, position=team.position_for(player.id).value)
                for player in team.players
            ]
            self.session.add(entity)
            self.session.flush()
            saved_ids.append(entity.id)
        self.session.commit()
        return saved_ids
