from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.base import Base
from app.opgg.client import OpggClient
from app.opgg.schemas import SeasonTierEntry
from app.riot.client import RiotAPIClient
from app.riot.schemas import ChampionMasteryEntry, MatchHistoryEntry, RankInfo, RiotAccount
from app.services.player_service import PlayerService
from app.utils.enums import Division, Position, Role, Tier


class FakeRiotAPIClient(RiotAPIClient):
    def get_account_by_riot_id(self, game_name: str, tag_line: str) -> RiotAccount:
        return RiotAccount(puuid="fake-puuid", game_name=game_name, tag_line=tag_line)

    def get_rank(self, puuid: str):
        return RankInfo(tier=Tier.GOLD, division=Division.I, lp=50, wins=10, losses=5)

    def has_ranked_solo_history(self, puuid: str) -> bool:
        return True

    def get_match_history(self, puuid: str, count: int = 20, start: int = 0) -> list[MatchHistoryEntry]:
        raise NotImplementedError

    def get_champion_mastery(self, puuid: str) -> list[ChampionMasteryEntry]:
        raise NotImplementedError


class FakeOpggClient(OpggClient):
    def __init__(self, entries: list[SeasonTierEntry] | None = None, raises: Exception | None = None) -> None:
        self._entries = entries or []
        self._raises = raises

    def get_season_history(self, game_name: str, tag_line: str, platform: str = "kr") -> list[SeasonTierEntry]:
        if self._raises is not None:
            raise self._raises
        return self._entries


@pytest.fixture
def session():
    from app.database import entities  # noqa: F401  registers tables on Base.metadata

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    with SessionLocal() as s:
        yield s


def test_fetch_peak_returns_none_when_no_season_history(session):
    service = PlayerService(session, server_id=1, opgg_client=FakeOpggClient(entries=[]))
    assert service.fetch_peak_from_opgg("GameName", "KR1") is None


def test_fetch_peak_returns_none_when_opgg_client_raises(session):
    service = PlayerService(session, server_id=1, opgg_client=FakeOpggClient(raises=ConnectionError("down")))
    assert service.fetch_peak_from_opgg("GameName", "KR1") is None


def test_fetch_peak_returns_none_when_opgg_not_implemented(session):
    service = PlayerService(session, server_id=1, opgg_client=FakeOpggClient(raises=NotImplementedError("no bs4")))
    assert service.fetch_peak_from_opgg("GameName", "KR1") is None


def test_fetch_peak_picks_the_highest_scoring_season_not_the_most_recent(session):
    entries = [
        SeasonTierEntry(season="S2025", tier=Tier.MASTER, division=Division.IV, lp=285),
        SeasonTierEntry(season="S2024 S2", tier=Tier.MASTER, division=Division.IV, lp=2066),  # rebased GM
        SeasonTierEntry(season="S2024 S1", tier=Tier.DIAMOND, division=Division.I, lp=40),
    ]
    service = PlayerService(session, server_id=1, opgg_client=FakeOpggClient(entries=entries))

    result = service.fetch_peak_from_opgg("GameName", "KR1")

    assert result is not None
    snapshot, season = result
    assert season == "S2024 S2"
    assert snapshot.tier == Tier.MASTER
    assert snapshot.lp == 2066


def test_register_player_stores_peak_achieved_season(session):
    service = PlayerService(session, server_id=1, riot_client=FakeRiotAPIClient())
    puuid, current = service.probe_current_season("GameName", "KR1")

    from app.rating.resolver import TierSnapshot

    peak = TierSnapshot(Tier.MASTER, Division.IV, 2066)
    player = service.register_player(
        "MyNick",
        puuid,
        Position.MID,
        current,
        peak=peak,
        actor_role=Role.SERVER_ADMIN,
        peak_achieved_season="S2024 S2",
    )

    assert player.peak_tier == Tier.MASTER
    assert player.peak_achieved_season == "S2024 S2"

    reloaded = service.get_player(player.id)
    assert reloaded.peak_achieved_season == "S2024 S2"


def test_register_player_leaves_peak_achieved_season_none_by_default(session):
    service = PlayerService(session, server_id=1, riot_client=FakeRiotAPIClient())
    puuid, current = service.probe_current_season("GameName", "KR1")

    player = service.register_player(
        "MyNick", puuid, Position.MID, current, peak=None, actor_role=Role.SERVER_ADMIN
    )

    assert player.peak_achieved_season is None
