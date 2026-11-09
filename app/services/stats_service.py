from __future__ import annotations

from collections import defaultdict

from sqlalchemy.orm import Session

from app.database.repositories.match_repository import MatchRepository
from app.database.repositories.player_repository import PlayerRepository
from app.models.match import Match
from app.models.player import Player
from app.utils.exceptions import PlayerNotFoundError

RECENT_MATCH_LIMIT = 20


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

    # --- records: win/loss and MVP counts from the recorded matches ---

    @staticmethod
    def _tally(player: Player, matches: list[Match]) -> dict[str, object]:
        wins = losses = ai_mvp = user_mvp = 0
        for match in matches:
            mine = next((p for p in match.participants if p.player_id == player.id), None)
            if mine is None:
                continue
            if mine.team_index == match.winning_team_index:
                wins += 1
            else:
                losses += 1
            ai_mvp += match.ai_mvp_player_id == player.id
            user_mvp += match.user_mvp_player_id == player.id
        return {
            "player_id": player.id,
            "nickname": player.nickname,
            "is_active": player.is_active,
            "final_rating": player.final_rating,
            "games": wins + losses,
            "wins": wins,
            "losses": losses,
            "ai_mvp": ai_mvp,
            "user_mvp": user_mvp,
        }

    def records(self) -> list[dict[str, object]]:
        """One row per player for the leaderboard, highest Final Rating
        first. Inactive players are kept only if they have played."""
        matches = self.match_repo.list()
        rows = [self._tally(p, matches) for p in self.player_repo.list(include_inactive=True)]
        rows = [r for r in rows if r["is_active"] or r["games"]]
        return sorted(rows, key=lambda r: r["final_rating"], reverse=True)

    def player_record(self, player_id: int) -> dict[str, object]:
        player = self.player_repo.get(player_id)  # raises PlayerNotFoundError
        if player.id is None:
            raise PlayerNotFoundError(f"존재하지 않는 참가자입니다 (#{player_id})")
        names = {p.id: p.nickname for p in self.player_repo.list(include_inactive=True)}
        mine = sorted(
            self.match_repo.list_for_player(player_id), key=lambda m: (m.played_at, m.id or 0)
        )

        positions: dict[str, dict[str, int]] = defaultdict(lambda: {"games": 0, "wins": 0})
        history = []
        recent = []
        for match in mine:
            me = next(p for p in match.participants if p.player_id == player_id)
            won = me.team_index == match.winning_team_index
            positions[me.position.value]["games"] += 1
            positions[me.position.value]["wins"] += won
            delta = (
                me.internal_rating_after - me.internal_rating_before
                if me.internal_rating_after is not None and me.internal_rating_before is not None
                else None
            )
            if delta is not None:
                history.append(
                    {
                        "match_id": match.id,
                        "played_at": match.played_at,
                        "won": won,
                        "rating_after": me.internal_rating_after,
                        "delta": delta,
                    }
                )
            recent.append(
                {
                    "match_id": match.id,
                    "played_at": match.played_at,
                    "won": won,
                    "position": me.position.value,
                    "delta": delta,
                    "ai_mvp": match.ai_mvp_player_id == player_id,
                    "user_mvp": match.user_mvp_player_id == player_id,
                    "teammates": [
                        names.get(p.player_id, f"#{p.player_id}")
                        for p in match.participants
                        if p.team_index == me.team_index and p.player_id != player_id
                    ],
                }
            )

        return {
            "record": self._tally(player, mine),
            "positions": [{"position": pos, **counts} for pos, counts in positions.items()],
            "rating_history": history,
            "recent": list(reversed(recent))[:RECENT_MATCH_LIMIT],
        }
