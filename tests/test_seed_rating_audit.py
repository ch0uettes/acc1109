from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.base import Base
from app.riot.client import RiotAPIClient
from app.riot.schemas import ChampionMasteryEntry, MatchHistoryEntry, RankInfo, RiotAccount
from app.services.player_service import PlayerService
from app.utils.enums import Position, Role, Tier


class UnrankedRiotAPIClient(RiotAPIClient):
    def get_account_by_riot_id(self, game_name: str, tag_line: str) -> RiotAccount:
        return RiotAccount(puuid="fake-puuid", game_name=game_name, tag_line=tag_line)

    def get_rank(self, puuid: str) -> RankInfo | None:
        return None

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


def test_initial_seed_rating_assignment_is_audited(session):
    service = PlayerService(session, server_id=1, riot_client=UnrankedRiotAPIClient())
    puuid, current = service.probe_current_season("Game", "KR1")

    player = service.register_player(
        "Newbie",
        puuid,
        Position.TOP,
        current,
        peak=None,
        actor_role=Role.SERVER_ADMIN,
        seed_tier=Tier.SILVER,
        changed_by="admin_alice",
        reason="첫 등록, 실력 추정",
    )

    history = service.seed_rating_history(player.id)
    assert len(history) == 1
    assert history[0].old_seed_rating is None
    assert history[0].new_seed_rating == player.seed_rating
    assert history[0].changed_by == "admin_alice"
    assert history[0].reason == "첫 등록, 실력 추정"


def test_seed_rating_change_is_audited_with_old_and_new_value(session):
    service = PlayerService(session, server_id=1, riot_client=UnrankedRiotAPIClient())
    puuid, current = service.probe_current_season("Game", "KR1")
    player = service.register_player(
        "Newbie",
        puuid,
        Position.TOP,
        current,
        peak=None,
        actor_role=Role.SERVER_ADMIN,
        seed_tier=Tier.SILVER,
        changed_by="admin_alice",
    )
    first_seed_rating = player.seed_rating

    updated = service.set_seed_rating(
        player.id,
        Tier.EMERALD,
        changed_by="admin_bob",
        actor_role=Role.SERVER_ADMIN,
        reason="실제 실력이 초기 추정보다 높다고 판단",
    )

    history = service.seed_rating_history(player.id)
    assert len(history) == 2
    latest = history[-1]
    assert latest.old_seed_rating == first_seed_rating
    assert latest.new_seed_rating == updated.seed_rating
    assert latest.changed_by == "admin_bob"
    assert latest.reason == "실제 실력이 초기 추정보다 높다고 판단"
    assert updated.seed_rating > first_seed_rating  # Emerald > Silver


def test_set_seed_rating_forces_unranked_tier_and_clears_official_rating(session):
    service = PlayerService(session, server_id=1, riot_client=UnrankedRiotAPIClient())
    puuid, current = service.probe_current_season("Game", "KR1")
    player = service.register_player(
        "Newbie",
        puuid,
        Position.TOP,
        current,
        peak=None,
        actor_role=Role.SERVER_ADMIN,
        seed_tier=Tier.SILVER,
        changed_by="admin",
    )

    updated = service.set_seed_rating(
        player.id, Tier.PLATINUM, changed_by="admin", actor_role=Role.SERVER_ADMIN
    )

    assert updated.tier == Tier.UNRANKED
    assert updated.official_rating is None
