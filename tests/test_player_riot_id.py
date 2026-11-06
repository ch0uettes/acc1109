from __future__ import annotations

from typing import Optional

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.base import Base
from app.riot.client import RiotAPIClient
from app.riot.schemas import ChampionMasteryEntry, MatchHistoryEntry, RankInfo, RiotAccount
from app.services.player_service import PlayerService
from app.utils.enums import Division, Position, Role, Tier

GOLD = RankInfo(tier=Tier.GOLD, division=Division.II, lp=45, wins=10, losses=5)


class FakeRiot(RiotAPIClient):
    def __init__(self, rank: Optional[RankInfo] = GOLD, current_id: Optional[tuple[str, str]] = ("플루오린", "0217")):
        self._rank = rank
        self._current_id = current_id

    def get_account_by_riot_id(self, game_name: str, tag_line: str) -> RiotAccount:
        return RiotAccount(puuid="puuid-1", game_name=game_name, tag_line=tag_line)

    def get_account_by_puuid(self, puuid: str) -> RiotAccount:
        if self._current_id is None:
            raise ConnectionError("lookup failed")
        return RiotAccount(puuid=puuid, game_name=self._current_id[0], tag_line=self._current_id[1])

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
    with sessionmaker(bind=engine)() as s:
        yield s


def test_register_stores_the_riot_id_looked_up(session):
    service = PlayerService(session, server_id=1, riot_client=FakeRiot())
    puuid, current = service.probe_current_season("플루오린", "0217")

    player = service.register_player(
        "허재혁", puuid, Position.MID, current, peak=None, actor_role=Role.SERVER_ADMIN,
        riot_game_name=" 플루오린 ", riot_tag_line="0217",
    )

    assert (player.riot_game_name, player.riot_tag_line) == ("플루오린", "0217")
    assert service.get_player(player.id).riot_game_name == "플루오린"


def test_refresh_fills_in_a_missing_riot_id(session):
    service = PlayerService(session, server_id=1, riot_client=FakeRiot(current_id=("새이름", "KR1")))
    puuid, current = service.probe_current_season("옛이름", "KR1")
    player = service.register_player("허재혁", puuid, Position.MID, current, peak=None, actor_role=Role.SERVER_ADMIN)
    assert player.riot_game_name is None

    refreshed, _ = service.refresh_from_riot(player.id, Role.SERVER_ADMIN)

    assert (refreshed.riot_game_name, refreshed.riot_tag_line) == ("새이름", "KR1")


def test_refresh_fills_the_riot_id_even_when_unranked(session):
    service = PlayerService(session, server_id=1, riot_client=FakeRiot())
    puuid, current = service.probe_current_season("플루오린", "0217")
    player = service.register_player("허재혁", puuid, Position.MID, current, peak=None, actor_role=Role.SERVER_ADMIN)
    service.riot_client = FakeRiot(rank=None)

    refreshed, message = service.refresh_from_riot(player.id, Role.SERVER_ADMIN)

    assert "언랭" in message
    assert refreshed.riot_game_name == "플루오린"


def test_a_failed_riot_id_lookup_does_not_break_the_rank_refresh(session):
    service = PlayerService(session, server_id=1, riot_client=FakeRiot())
    puuid, current = service.probe_current_season("플루오린", "0217")
    player = service.register_player(
        "허재혁", puuid, Position.MID, current, peak=None, actor_role=Role.SERVER_ADMIN,
        riot_game_name="플루오린", riot_tag_line="0217",
    )
    service.riot_client = FakeRiot(rank=RankInfo(tier=Tier.PLATINUM, division=Division.IV, lp=0, wins=1, losses=0), current_id=None)

    refreshed, _ = service.refresh_from_riot(player.id, Role.SERVER_ADMIN)

    assert refreshed.tier == Tier.PLATINUM
    assert refreshed.riot_game_name == "플루오린"
