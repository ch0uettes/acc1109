from __future__ import annotations

from sqlalchemy.orm import Session

from app.database.repositories.match_repository import MatchRepository
from app.database.repositories.player_repository import PlayerRepository
from app.models.match import Match
from app.models.player import Player


class StatsService:
    def __init__(self, session: Session, server_id: int) -> None:
        self.player_repo = PlayerRepository(session, server_id)
        self.match_repo = MatchRepository(session, server_id)

    def leaderboard(self) -> list[Player]:
        return sorted(self.player_repo.list(), key=lambda p: p.final_rating, reverse=True)

    def player_match_history(self, player_id: int) -> list[Match]:
        return self.match_repo.list_for_player(player_id)

    def ai_mvp_accuracy(self) -> float:
        matches = self.match_repo.list()
        judged = [m for m in matches if m.user_mvp_player_id is not None]
        if not judged:
            return 0.0
        correct = sum(1 for m in judged if m.ai_mvp_player_id == m.user_mvp_player_id)
        return correct / len(judged)
