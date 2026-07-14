from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.base import Base
from app.models.player import Player
from app.services.player_service import PlayerService
from app.utils.enums import Division, Position, Role, Tier


@pytest.fixture
def session():
    from app.database import entities  # noqa: F401  registers tables on Base.metadata

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    with SessionLocal() as s:
        yield s


def _player(nickname: str) -> Player:
    return Player(nickname=nickname, tier=Tier.GOLD, division=Division.I, lp=0, main_role=Position.MID)


def test_same_nickname_allowed_across_different_servers(session):
    server_a = PlayerService(session, server_id=1)
    server_b = PlayerService(session, server_id=2)

    server_a.create_player(_player("승부사"), actor_role=Role.SERVER_ADMIN)
    # must not raise a UNIQUE constraint error - different servers, same nickname
    server_b.create_player(_player("승부사"), actor_role=Role.SERVER_ADMIN)

    assert len(server_a.list_players()) == 1
    assert len(server_b.list_players()) == 1


def test_players_are_isolated_between_servers(session):
    server_a = PlayerService(session, server_id=1)
    server_b = PlayerService(session, server_id=2)

    server_a.create_player(_player("PlayerA"), actor_role=Role.SERVER_ADMIN)
    server_b.create_player(_player("PlayerB"), actor_role=Role.SERVER_ADMIN)

    assert [p.nickname for p in server_a.list_players()] == ["PlayerA"]
    assert [p.nickname for p in server_b.list_players()] == ["PlayerB"]


def test_cannot_fetch_another_servers_player_by_id(session):
    from app.utils.exceptions import PlayerNotFoundError

    server_a = PlayerService(session, server_id=1)
    server_b = PlayerService(session, server_id=2)

    created = server_a.create_player(_player("OnlyInA"), actor_role=Role.SERVER_ADMIN)

    with pytest.raises(PlayerNotFoundError):
        server_b.get_player(created.id)


def test_internal_rating_is_independent_per_server_for_same_puuid(session):
    server_a = PlayerService(session, server_id=1)
    server_b = PlayerService(session, server_id=2)

    player_a = server_a.create_player(
        Player(nickname="X", puuid="same-puuid", tier=Tier.GOLD, division=Division.I, lp=0, main_role=Position.MID),
        actor_role=Role.SERVER_ADMIN,
    )
    player_b = server_b.create_player(
        Player(nickname="X", puuid="same-puuid", tier=Tier.GOLD, division=Division.I, lp=0, main_role=Position.MID),
        actor_role=Role.SERVER_ADMIN,
    )

    server_a.repo.update_internal_rating(player_a.id, 2120.0)
    server_b.repo.update_internal_rating(player_b.id, 1950.0)

    assert server_a.get_player(player_a.id).internal_rating == 2120.0
    assert server_b.get_player(player_b.id).internal_rating == 1950.0
