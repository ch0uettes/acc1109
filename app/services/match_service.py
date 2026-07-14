from __future__ import annotations

import statistics
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.ai.contribution import ContributionScoreCalculator, DummyContributionScoreCalculator
from app.ai.mvp import AIMVPSelector
from app.database.repositories.match_repository import MatchRepository
from app.database.repositories.player_repository import PlayerRepository
from app.models.match import Match, MatchPlayerResult
from app.models.player import Player
from app.models.team import Team
from app.rating.updater import (
    CALIBRATION_GAME_THRESHOLD,
    ExpectedPerformanceUpdateStrategy,
    MatchRatingContext,
    RatingUpdateStrategy,
)
from app.services.rbac import Permission, require_permission
from app.utils.enums import Position, Role


class MatchService:
    def __init__(
        self,
        session: Session,
        server_id: int,
        contribution_calculator: ContributionScoreCalculator | None = None,
        mvp_selector: AIMVPSelector | None = None,
        rating_updater: RatingUpdateStrategy | None = None,
    ) -> None:
        self.match_repo = MatchRepository(session, server_id)
        self.player_repo = PlayerRepository(session, server_id)
        self.contribution_calculator = contribution_calculator or DummyContributionScoreCalculator()
        self.mvp_selector = mvp_selector or AIMVPSelector()
        self.rating_updater = rating_updater or ExpectedPerformanceUpdateStrategy()

    def record_match(
        self,
        teams: list[Team],
        winning_team_index: int,
        actor_role: Role,
        note: str | None = None,
        match_stats_by_player_id: dict[int, dict] | None = None,
    ) -> Match:
        require_permission(actor_role, Permission.CREATE_MATCH)
        match_stats_by_player_id = match_stats_by_player_id or {}
        positions_by_player_id = {
            player.id: team.position_for(player.id) for team in teams for player in team.players
        }
        participants: list[MatchPlayerResult] = []
        for team in teams:
            for player in team.players:
                stats = match_stats_by_player_id.get(player.id, {})
                contribution = self.contribution_calculator.calculate(player, stats)
                participants.append(
                    MatchPlayerResult(
                        player_id=player.id,
                        team_index=team.index,
                        position=positions_by_player_id[player.id],
                        contribution=contribution,
                    )
                )

        ai_mvp_id = self.mvp_selector.select(participants)
        match = Match(
            played_at=datetime.utcnow(),
            participants=participants,
            winning_team_index=winning_team_index,
            ai_mvp_player_id=ai_mvp_id,
            note=note,
        )
        saved = self.match_repo.add(match)
        self._update_internal_ratings(teams, winning_team_index, participants, positions_by_player_id)
        return saved

    def _update_internal_ratings(
        self,
        teams: list[Team],
        winning_team_index: int,
        participants: list[MatchPlayerResult],
        positions_by_player_id: dict[int, Position],
    ) -> None:
        contribution_by_player_id = {p.player_id: p.contribution.total for p in participants}

        for team in teams:
            won = team.index == winning_team_index
            other_players = [p for t in teams if t.index != team.index for p in t.players]

            for player in team.players:
                opponent_rating, opponent_contribution = self._find_opponent_reference(
                    player, other_players, contribution_by_player_id, positions_by_player_id
                )
                context = MatchRatingContext(
                    won=won,
                    own_contribution=contribution_by_player_id.get(player.id, 0.0),
                    opponent_final_rating=opponent_rating,
                    opponent_contribution=opponent_contribution,
                )
                new_internal = self.rating_updater.update(player, context)
                exit_calibration = (
                    player.calibration_mode and (player.games_played + 1) >= CALIBRATION_GAME_THRESHOLD
                )
                self.player_repo.update_internal_rating(
                    player.id, new_internal, exit_calibration=exit_calibration
                )

    def _find_opponent_reference(
        self,
        player: Player,
        other_players: list[Player],
        contribution_by_player_id: dict[int, float],
        positions_by_player_id: dict[int, Position],
    ) -> tuple[float, float]:
        """A same-*assigned*-position ("맞라인") opponent when exactly one
        exists on the other side(s); otherwise the pooled average of all
        other players, since our current roster's position data isn't
        always clean enough to guarantee a 1:1 lane match. Uses the lane
        each player was actually assigned for this match (positions_by_
        player_id, from Team.position_for) rather than their profile
        main_role, so a player placed on Sub/Other for this game gets
        matched against the right lane opponent."""
        player_position = positions_by_player_id[player.id]
        same_position = [p for p in other_players if positions_by_player_id[p.id] == player_position]
        if len(same_position) == 1:
            opponent = same_position[0]
            return opponent.final_rating, contribution_by_player_id.get(opponent.id, 0.0)

        if not other_players:
            return player.final_rating, contribution_by_player_id.get(player.id, 0.0)

        avg_rating = statistics.fmean(p.final_rating for p in other_players)
        avg_contribution = statistics.fmean(
            contribution_by_player_id.get(p.id, 0.0) for p in other_players
        )
        return avg_rating, avg_contribution

    def set_user_mvp(self, match_id: int, player_id: int, actor_role: Role) -> None:
        require_permission(actor_role, Permission.CONFIRM_AI_MVP)
        self.match_repo.set_user_mvp(match_id, player_id)

    def get_match(self, match_id: int) -> Match | None:
        return self.match_repo.get(match_id)

    def list_pending_votes(self) -> list[Match]:
        """Matches that haven't had a User MVP decided yet."""
        return [m for m in self.match_repo.list() if m.user_mvp_player_id is None]
