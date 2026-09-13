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
from app.utils.exceptions import AppError


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


def _register(service: PlayerService, nickname: str, rank: Optional[RankInfo]) -> Player:
    puuid, current = service.probe_current_season("Game", "KR1")
    return service.register_player(nickname, puuid, Position.MID, current, peak=None, actor_role=Role.SERVER_ADMIN)


# --- register_player: reactivate-instead-of-duplicate ---


def test_register_player_rejects_a_duplicate_of_an_active_player(session):
    rank = RankInfo(tier=Tier.GOLD, division=Division.II, lp=45, wins=10, losses=5)
    service = PlayerService(session, server_id=1, riot_client=FakeRiotAPIClient(rank))
    _register(service, "대상", rank)

    with pytest.raises(AppError):
        _register(service, "대상", rank)


def test_register_player_links_an_existing_manual_entry_with_the_same_nickname(session):
    """Regression test for a real-world case found via a production data
    export: a server often already has an older manual-entry ("직접 입력")
    player under a common name (no puuid at all, since manual entry never
    has one) before that same real person is ever registered through
    Riot ID lookup. That must be treated as linking their real account to
    the same identity, not a genuine duplicate - the manual entry has
    nothing to conflict with (nickname is this server's only identity
    signal for a puuid-less row) and a "no puuid, use 정보 새로고침 instead"
    dead end would leave no way to ever attach a Riot account at all."""
    service = PlayerService(session, server_id=1)
    manual = service.create_player(
        Player(nickname="강민수", tier=Tier.SILVER, division=Division.IV, lp=48, main_role=Position.MID),
        actor_role=Role.SERVER_ADMIN,
    )
    assert manual.puuid is None

    rank = RankInfo(tier=Tier.GOLD, division=Division.II, lp=45, wins=10, losses=5)
    service.riot_client = FakeRiotAPIClient(rank)
    linked = _register(service, "강민수", rank)

    assert linked.id == manual.id  # same row, now linked - not a rejected duplicate
    assert linked.puuid == "fake-puuid"
    assert linked.tier == Tier.GOLD
    assert linked.rating_source == RatingSource.CURRENT_SEASON


def test_register_player_revives_a_deactivated_player_by_puuid(session):
    """Regression test for the reported bug: re-registering someone whose
    old row was soft-deleted used to hit the (server_id, puuid) unique
    constraint and crash with a raw IntegrityError ("이미 존재하는 참가자"),
    even though they're gone from the visible roster. It now revives that
    same row (same puuid) with fresh data instead."""
    old_rank = RankInfo(tier=Tier.GOLD, division=Division.II, lp=45, wins=10, losses=5)
    service = PlayerService(session, server_id=1, riot_client=FakeRiotAPIClient(old_rank))
    original = _register(service, "임도현", old_rank)
    service.override_internal_rating(original.id, 300.0, actor_role=Role.SERVER_ADMIN, changed_by="admin")
    service.deactivate_player(original.id, actor_role=Role.SERVER_ADMIN)

    new_rank = RankInfo(tier=Tier.DIAMOND, division=Division.I, lp=10, wins=20, losses=10)
    service_new_rank = PlayerService(session, server_id=1, riot_client=FakeRiotAPIClient(new_rank))
    revived = _register(service_new_rank, "임도현", new_rank)

    assert revived.id == original.id
    assert revived.is_active is True
    assert revived.tier == Tier.DIAMOND
    assert revived.internal_rating == 300.0
    assert original.id in {p.id for p in service.list_players()}


# --- refresh_from_riot ---


def test_refresh_from_riot_updates_tier_and_official_rating(session):
    old_rank = RankInfo(tier=Tier.GOLD, division=Division.II, lp=45, wins=10, losses=5)
    service = PlayerService(session, server_id=1, riot_client=FakeRiotAPIClient(old_rank))
    player = _register(service, "대상", old_rank)

    new_rank = RankInfo(tier=Tier.DIAMOND, division=Division.III, lp=20, wins=20, losses=10)
    service.riot_client = FakeRiotAPIClient(new_rank)

    refreshed, message = service.refresh_from_riot(player.id, actor_role=Role.SERVER_ADMIN)

    assert refreshed.tier == Tier.DIAMOND
    assert refreshed.division == Division.III
    assert refreshed.lp == 20
    assert refreshed.rating_source == RatingSource.CURRENT_SEASON
    assert "최신 랭크로 갱신했습니다" in message


def test_refresh_from_riot_leaves_data_untouched_when_now_unranked(session):
    old_rank = RankInfo(tier=Tier.GOLD, division=Division.II, lp=45, wins=10, losses=5)
    service = PlayerService(session, server_id=1, riot_client=FakeRiotAPIClient(old_rank))
    player = _register(service, "대상", old_rank)

    service.riot_client = FakeRiotAPIClient(rank=None)

    refreshed, message = service.refresh_from_riot(player.id, actor_role=Role.SERVER_ADMIN)

    assert refreshed.tier == Tier.GOLD  # unchanged - never silently guessed
    assert "언랭 상태" in message


def test_refresh_from_riot_surfaces_a_missing_api_key_as_a_clean_error(session):
    """Regression test: refresh_from_riot() must never let a raw
    NotImplementedError/requests exception reach the UI uncaught - the
    same 'never raises, always optional' contract this app already
    applies to peak-tier lookups and position inference is nowhere near
    as defensible for the refresh action itself (it's the whole point of
    the button), but it must still surface as a normal, catchable
    AppError instead of crashing the page."""
    old_rank = RankInfo(tier=Tier.GOLD, division=Division.II, lp=45, wins=10, losses=5)
    service = PlayerService(session, server_id=1, riot_client=FakeRiotAPIClient(old_rank))
    player = _register(service, "대상", old_rank)

    class NoKeyRiotAPIClient(FakeRiotAPIClient):
        def get_rank(self, puuid: str) -> Optional[RankInfo]:
            raise NotImplementedError("RIOT_API_KEY is not configured")

    service.riot_client = NoKeyRiotAPIClient(rank=None)

    with pytest.raises(AppError):
        service.refresh_from_riot(player.id, actor_role=Role.SERVER_ADMIN)


def test_refresh_from_riot_rejects_a_manual_entry_player(session):
    service = PlayerService(session, server_id=1)

    player = service.create_player(
        Player(nickname="수동입력", tier=Tier.GOLD, division=Division.I, lp=0, main_role=Position.MID),
        actor_role=Role.SERVER_ADMIN,
    )

    with pytest.raises(AppError):
        service.refresh_from_riot(player.id, actor_role=Role.SERVER_ADMIN)
