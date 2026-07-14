from __future__ import annotations

from typing import Optional

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.base import Base
from app.models.player import Player
from app.riot.client import RiotAPIClient
from app.riot.schemas import ChampionMasteryEntry, MatchHistoryEntry, RankInfo, RiotAccount
from app.services.player_service import PlayerService
from app.utils.enums import Division, Position, RatingSource, Role, Tier


class FakeRiotAPIClient(RiotAPIClient):
    def __init__(self, rank: Optional[RankInfo]) -> None:
        self._rank = rank

    def get_account_by_riot_id(self, game_name: str, tag_line: str) -> RiotAccount:
        return RiotAccount(puuid="fake-puuid", game_name=game_name, tag_line=tag_line)

    def get_rank(self, puuid: str) -> Optional[RankInfo]:
        return self._rank

    def has_ranked_solo_history(self, puuid: str) -> bool:
        return False

    def get_match_history(self, puuid: str, count: int = 20, start: int = 0) -> list[MatchHistoryEntry]:
        raise NotImplementedError

    def get_champion_mastery(self, puuid: str) -> list[ChampionMasteryEntry]:
        raise NotImplementedError


@pytest.fixture
def session():
    from app.database import entities  # noqa: F401  registers tables on Base.metadata

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    with SessionLocal() as s:
        yield s


def test_probe_current_season_returns_snapshot_when_ranked(session):
    rank = RankInfo(tier=Tier.DIAMOND, division=Division.II, lp=70, wins=10, losses=5)
    service = PlayerService(session, server_id=1, riot_client=FakeRiotAPIClient(rank))

    puuid, current = service.probe_current_season("GameName", "KR1")

    assert puuid == "fake-puuid"
    assert current is not None
    assert current.tier == Tier.DIAMOND
    assert current.lp == 70


def test_probe_current_season_returns_none_when_unranked(session):
    service = PlayerService(session, server_id=1, riot_client=FakeRiotAPIClient(rank=None))

    _, current = service.probe_current_season("GameName", "KR1")

    assert current is None


def test_register_player_with_current_rank_only(session):
    rank = RankInfo(tier=Tier.DIAMOND, division=Division.II, lp=70, wins=10, losses=5)
    service = PlayerService(session, server_id=1, riot_client=FakeRiotAPIClient(rank))
    puuid, current = service.probe_current_season("GameName", "KR1")

    player = service.register_player(
        "MyNick", puuid, Position.MID, current, peak=None, actor_role=Role.SERVER_ADMIN
    )

    assert player.puuid == "fake-puuid"
    assert player.tier == Tier.DIAMOND
    assert player.official_rating == 2400 + 200 + 70
    assert player.rating_source == RatingSource.CURRENT_SEASON


def test_register_player_unranked_without_seed_tier_raises(session):
    """Nobody self-reports their own skill - if there's no current-season
    rank, an operator-assigned seed_tier is mandatory."""
    service = PlayerService(session, server_id=1, riot_client=FakeRiotAPIClient(rank=None))
    puuid, current = service.probe_current_season("GameName", "KR1")
    assert current is None

    with pytest.raises(ValueError):
        service.register_player(
            "Unranked", puuid, Position.SUPPORT, current=None, peak=None, actor_role=Role.SERVER_ADMIN
        )


def test_register_player_unranked_uses_operator_seed_tier(session):
    service = PlayerService(session, server_id=1, riot_client=FakeRiotAPIClient(rank=None))
    puuid, current = service.probe_current_season("GameName", "KR1")
    assert current is None

    player = service.register_player(
        "Unranked",
        puuid,
        Position.SUPPORT,
        current=None,
        peak=None,
        seed_tier=Tier.GOLD,
        actor_role=Role.SERVER_ADMIN,
    )

    assert player.tier == Tier.UNRANKED
    assert player.rating_source == RatingSource.SEED
    assert player.calibration_mode is True
    assert player.official_rating is None
    assert player.seed_rating is not None
    assert 1200 < player.seed_rating < 1600  # somewhere inside Gold's span
