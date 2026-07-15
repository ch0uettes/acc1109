from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.database.repositories.player_repository import PlayerRepository
from app.database.repositories.season_rank_repository import SeasonRankRepository
from app.database.repositories.seed_rating_change_repository import SeedRatingChangeRepository
from app.models.player import Player
from app.models.season_rank import PlayerSeasonRank
from app.models.seed_rating_change import SeedRatingChange
from app.position.analyzer import PositionAnalyzer, RiotHistoryPositionAnalyzer
from app.position.schemas import RoleRecommendation
from app.rating.official_strategy import CurrentTierPriorityStrategy, OfficialRatingStrategy
from app.rating.resolver import RatingCaseResolver, RatingResolution, TierSnapshot, seed_rating_for_tier
from app.riot.client import RiotAPIClient, build_riot_client
from app.services.rbac import Permission, require_permission
from app.utils.enums import Division, Position, RatingSource, Role, Tier


class PlayerService:
    """Scoped to one Server: every read/write goes through repositories
    bound to `server_id`, so a service built for Server A structurally
    cannot see or mutate Server B's players."""

    def __init__(
        self,
        session: Session,
        server_id: int,
        riot_client: Optional[RiotAPIClient] = None,
        official_rating_strategy: Optional[OfficialRatingStrategy] = None,
        position_analyzer: Optional[PositionAnalyzer] = None,
    ) -> None:
        self.server_id = server_id
        self.repo = PlayerRepository(session, server_id)
        self.season_rank_repo = SeasonRankRepository(session, server_id)
        self.seed_rating_change_repo = SeedRatingChangeRepository(session)
        self.official_rating_strategy = official_rating_strategy or CurrentTierPriorityStrategy()
        self.riot_client = riot_client or build_riot_client()
        self.position_analyzer = position_analyzer or RiotHistoryPositionAnalyzer(self.riot_client)

    def create_player(self, player: Player, actor_role: Role) -> Player:
        """Manual-entry path: the operator has typed an exact current tier
        they know to be true. `player.tier` must not be UNRANKED here - an
        operator who doesn't know a real tier should assign a Seed Rating
        via register_player(..., seed_tier=...) instead."""
        require_permission(actor_role, Permission.MANAGE_PLAYERS)
        player.official_rating = self.official_rating_strategy.calculate(player)
        saved = self.repo.add(player)
        self._record_season_snapshot(saved)
        return saved

    def probe_current_season(self, game_name: str, tag_line: str) -> tuple[str, Optional[TierSnapshot]]:
        """Riot ID -> PUUID + current-season rank (or None if unranked).
        Peak Tier is never auto-fetched here - Riot has no historical-peak
        endpoint - and it's metadata only regardless, never a scoring input."""
        account = self.riot_client.get_account_by_riot_id(game_name, tag_line)
        rank = self.riot_client.get_rank(account.puuid)
        current = TierSnapshot(rank.tier, rank.division, rank.lp) if rank else None
        return account.puuid, current

    def infer_position(self, puuid: str) -> Optional[RoleRecommendation]:
        """Main/Sub role recommendation from recent ranked match history, or
        None if the account has no ranked history to infer from at all.
        Reference-only: never applied automatically after registration."""
        return self.position_analyzer.recommend(puuid)

    def register_player(
        self,
        nickname: str,
        puuid: str,
        main_role: Position,
        current: Optional[TierSnapshot],
        peak: Optional[TierSnapshot],
        actor_role: Role = Role.PLAYER,
        seed_tier: Optional[Tier] = None,
        seed_division: Division = Division.III,
        changed_by: str = "unknown",
        reason: Optional[str] = None,
        sub_role: Optional[Position] = None,
        recommendation: Optional[RoleRecommendation] = None,
    ) -> Player:
        """Case 1 (current is not None): Official Rating from Riot data.
        Case 2/3 (current is None): the operator's `seed_tier` (+ optional
        `seed_division` for precision) judgment becomes the Seed Rating -
        required in that branch, since this project never lets a player
        self-report their own skill. Every Seed Rating assignment is
        audited, including this very first one.

        `recommendation` (from infer_position) seeds `main_role`/`sub_role`'s
        permanent reference fields exactly once, here - it's never written
        again after this call, matching the "Riot recommends, Profile
        decides" priority order."""
        require_permission(actor_role, Permission.MANAGE_PLAYERS)
        resolver = RatingCaseResolver(self.official_rating_strategy)
        if current is not None:
            resolution = resolver.resolve_current_season(current, peak)
        else:
            if seed_tier is None:
                raise ValueError(
                    "No current-season rank was found - an operator-assigned seed_tier is required"
                )
            require_permission(actor_role, Permission.SET_SEED_RATING)
            resolution = resolver.resolve_seed(seed_tier, peak, seed_division)

        player = self._build_player_from_resolution(
            nickname, puuid, main_role, resolution, sub_role, recommendation
        )
        saved = self.repo.add(player)
        self._record_season_snapshot(saved)
        if resolution.rating_source == RatingSource.SEED:
            self._log_seed_rating_change(saved.id, None, resolution.seed_rating, changed_by, reason)
        return saved

    def set_seed_rating(
        self,
        player_id: int,
        seed_tier: Tier,
        changed_by: str,
        actor_role: Role,
        seed_division: Division = Division.III,
        reason: Optional[str] = None,
    ) -> Player:
        """The only path that changes an existing player's Seed Rating.
        Always audited: old value, new value, who, when, why."""
        require_permission(actor_role, Permission.SET_SEED_RATING)
        player = self.repo.get(player_id)
        old_seed_rating = player.seed_rating
        new_seed_rating = seed_rating_for_tier(seed_tier, seed_division)

        updated = player.model_copy(
            update={
                "tier": Tier.UNRANKED,
                "official_rating": None,
                "seed_rating": new_seed_rating,
                "rating_source": RatingSource.SEED,
            }
        )
        saved = self.repo.update(updated)
        self._record_season_snapshot(saved)
        self._log_seed_rating_change(player_id, old_seed_rating, new_seed_rating, changed_by, reason)
        return saved

    def override_internal_rating(self, player_id: int, new_internal_rating: float, actor_role: Role) -> Player:
        """Manual admin override of internal_rating - the normal path is
        earned automatically through match results (see
        rating.updater.ExpectedPerformanceUpdateStrategy), never
        operator-typed. This exists for correcting a clearly-wrong value
        (e.g. a calibration bug, or a player who's obviously stronger/
        weaker than their earned Internal Rating suggests) - same
        permission tier as set_seed_rating() since both let an operator's
        judgment override a normally-computed rating."""
        require_permission(actor_role, Permission.SET_SEED_RATING)
        player = self.repo.get(player_id)
        updated = player.model_copy(update={"internal_rating": new_internal_rating})
        return self.repo.update(updated)

    def _log_seed_rating_change(
        self,
        player_id: int,
        old_seed_rating: Optional[float],
        new_seed_rating: float,
        changed_by: str,
        reason: Optional[str],
    ) -> None:
        self.seed_rating_change_repo.add(
            SeedRatingChange(
                player_id=player_id,
                server_id=self.server_id,
                old_seed_rating=old_seed_rating,
                new_seed_rating=new_seed_rating,
                changed_by=changed_by,
                changed_at=datetime.utcnow(),
                reason=reason,
            )
        )

    def seed_rating_history(self, player_id: int) -> list[SeedRatingChange]:
        return self.seed_rating_change_repo.list_for_player(player_id)

    def apply_resolution(self, player_id: int, resolution: RatingResolution, actor_role: Role) -> Player:
        """Re-resolves an existing player's rating fields (e.g. fixing a
        record created before this rating logic existed) without touching
        nickname/puuid/main_role/sub_role/internal_rating/games_played. Does NOT log
        a SeedRatingChange - this is a data-correction utility, not an
        operator judgment call; use set_seed_rating() for that."""
        require_permission(actor_role, Permission.MANAGE_PLAYERS)
        player = self.repo.get(player_id)
        updated = player.model_copy(
            update={
                "tier": resolution.tier,
                "division": resolution.division,
                "lp": resolution.lp,
                "peak_tier": resolution.peak_tier,
                "peak_division": resolution.peak_division,
                "peak_lp": resolution.peak_lp,
                "official_rating": resolution.official_rating,
                "seed_rating": resolution.seed_rating,
                "rating_source": resolution.rating_source,
                "confidence": resolution.confidence,
                "calibration_mode": resolution.calibration_mode,
            }
        )
        saved = self.repo.update(updated)
        self._record_season_snapshot(saved)
        return saved

    def _build_player_from_resolution(
        self,
        nickname: str,
        puuid: str,
        main_role: Position,
        resolution: RatingResolution,
        sub_role: Optional[Position] = None,
        recommendation: Optional[RoleRecommendation] = None,
    ) -> Player:
        return Player(
            nickname=nickname,
            puuid=puuid,
            tier=resolution.tier,
            division=resolution.division,
            lp=resolution.lp,
            peak_tier=resolution.peak_tier,
            peak_division=resolution.peak_division,
            peak_lp=resolution.peak_lp,
            official_rating=resolution.official_rating,
            seed_rating=resolution.seed_rating,
            rating_source=resolution.rating_source,
            confidence=resolution.confidence,
            calibration_mode=resolution.calibration_mode,
            main_role=main_role,
            sub_role=sub_role,
            recommended_main_role=recommendation.main if recommendation else None,
            recommended_main_confidence=recommendation.main_ratio if recommendation else None,
            recommended_sub_role=recommendation.sub if recommendation else None,
            recommended_sub_confidence=recommendation.sub_ratio if recommendation else None,
        )

    def _record_season_snapshot(self, player: Player) -> None:
        assert player.id is not None
        self.season_rank_repo.add(
            PlayerSeasonRank(
                player_id=player.id,
                season=settings.current_season_label,
                current_tier=player.tier,
                current_division=player.division,
                current_lp=player.lp,
                peak_tier=player.peak_tier,
                peak_division=player.peak_division,
                peak_lp=player.peak_lp,
                recorded_at=datetime.utcnow(),
            )
        )

    def get_player(self, player_id: int) -> Player:
        return self.repo.get(player_id)

    def list_players(self) -> list[Player]:
        return self.repo.list()

    def season_rank_history(self, player_id: int) -> list[PlayerSeasonRank]:
        return self.season_rank_repo.list_for_player(player_id)

    def update_player(self, player: Player, actor_role: Role) -> Player:
        """Non-Seed edits only (tier/division/lp/main_role/sub_role/peak).
        Changing seed_rating here is intentionally not supported - use
        set_seed_rating() so the change is always audited."""
        require_permission(actor_role, Permission.MANAGE_PLAYERS)
        player.official_rating = self.official_rating_strategy.calculate(player)
        saved = self.repo.update(player)
        self._record_season_snapshot(saved)
        return saved

    def delete_player(self, player_id: int, actor_role: Role) -> None:
        require_permission(actor_role, Permission.MANAGE_PLAYERS)
        self.repo.delete(player_id)
