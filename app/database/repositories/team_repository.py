from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.database.entities.team import TeamEntity, TeamPlayerEntity
from app.database.repositories.base import BaseRepository
from app.models.team import Team


class TeamRepository(BaseRepository[TeamEntity]):
    def __init__(self, session: Session, server_id: int) -> None:
        super().__init__(session, TeamEntity)
        self.server_id = server_id

    def _next_unique_generated_at(self) -> datetime:
        """`generated_at` is this server's only run identity (see
        save_generated_teams's docstring) - two calls landing on the same
        value would make get_run() silently merge two unrelated saves into
        one roster. datetime.utcnow() alone doesn't guarantee that: system
        clock resolution (observed directly - two calls in quick
        succession, e.g. an operator saving two combos back to back,
        landed on the exact same microsecond on Windows) can produce a
        collision. Bumping forward by 1us past this server's latest
        recorded run whenever the clock hasn't visibly advanced makes
        every run strictly after the previous one, at negligible cost
        (one indexed lookup) since saves are rare, human-paced actions."""
        candidate = datetime.utcnow()
        latest = (
            self.session.query(TeamEntity.generated_at)
            .filter(TeamEntity.server_id == self.server_id)
            .order_by(TeamEntity.generated_at.desc())
            .first()
        )
        if latest is not None and candidate <= latest[0]:
            candidate = latest[0] + timedelta(microseconds=1)
        return candidate

    def save_generated_teams(self, teams: list[Team]) -> list[int]:
        """Persists one balancer run. All rows share `generated_at` so a
        later query can group them back into one run without a batch table."""
        generated_at = self._next_unique_generated_at()
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

    def list_runs(self, limit: int = 20) -> list[datetime]:
        """Distinct `generated_at` values this server has saved, most
        recent first - each one identifies one save_generated_teams() call
        (see its own docstring on why every row from one call shares this
        value)."""
        rows = (
            self.session.query(TeamEntity.generated_at)
            .filter(TeamEntity.server_id == self.server_id)
            .distinct()
            .order_by(TeamEntity.generated_at.desc())
            .limit(limit)
            .all()
        )
        return [row[0] for row in rows]

    def get_run(self, generated_at: datetime) -> list[tuple[int, list[tuple[int, str]]]]:
        """Raw (team_index, [(player_id, position), ...]) for every team
        saved under one `generated_at` - deliberately no Player lookup
        here (that crosses into PlayerRepository's job); see
        TeamService.load_saved_run for the assembled, display-ready
        version."""
        entities = (
            self.session.query(TeamEntity)
            .filter(TeamEntity.server_id == self.server_id, TeamEntity.generated_at == generated_at)
            .order_by(TeamEntity.team_index)
            .all()
        )
        return [
            (entity.team_index, [(tp.player_id, tp.position) for tp in entity.team_players])
            for entity in entities
        ]
