from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.database.base import Base
from app.services.player_service import PlayerService
from app.services.server_service import ServerService
from app.utils.enums import Division, Position, Role, Tier
from app.utils.exceptions import PermissionDeniedError
from app.models.player import Player


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


def test_new_server_defaults_to_the_settings_season_label(session):
    service = ServerService(session)
    server = service.create_server("테스트 서버", owner_display_name="홍길동")

    assert server.current_season_label == settings.current_season_label


def test_owner_can_update_and_reload_season_label(session):
    service = ServerService(session)
    server = service.create_server("테스트 서버", owner_display_name="홍길동")

    updated = service.update_season_label(server.id, "홍길동", "2026-S1")
    assert updated.current_season_label == "2026-S1"

    reloaded = service.get_server(server.id)
    assert reloaded.current_season_label == "2026-S1"


def test_non_owner_cannot_update_season_label(session):
    service = ServerService(session)
    server = service.create_server("테스트 서버", owner_display_name="홍길동")
    service.add_player_member(server.id, "일반유저")

    with pytest.raises(PermissionDeniedError):
        service.update_season_label(server.id, "일반유저", "2026-S1")


def test_player_season_snapshot_uses_the_servers_season_label(session):
    server_service = ServerService(session)
    server = server_service.create_server("테스트 서버", owner_display_name="홍길동")
    server_service.update_season_label(server.id, "홍길동", "2026-S1")

    player_service = PlayerService(session, server_id=server.id)
    player = player_service.create_player(_player("대상"), actor_role=Role.SERVER_ADMIN)

    history = player_service.season_rank_history(player.id)
    assert len(history) == 1
    assert history[0].season == "2026-S1"


def test_new_server_defaults_to_empty_constraint_priorities(session):
    service = ServerService(session)
    server = service.create_server("테스트 서버", owner_display_name="홍길동")

    assert server.constraint_priorities == {}


def test_owner_can_update_and_reload_constraint_priorities(session):
    service = ServerService(session)
    server = service.create_server("테스트 서버", owner_display_name="홍길동")

    updated = service.update_constraint_priorities(server.id, "홍길동", {"fixed_role": 999})
    assert updated.constraint_priorities == {"fixed_role": 999}

    reloaded = service.get_server(server.id)
    assert reloaded.constraint_priorities == {"fixed_role": 999}


def test_non_owner_cannot_update_constraint_priorities(session):
    service = ServerService(session)
    server = service.create_server("테스트 서버", owner_display_name="홍길동")
    service.add_player_member(server.id, "일반유저")

    with pytest.raises(PermissionDeniedError):
        service.update_constraint_priorities(server.id, "일반유저", {"fixed_role": 999})


def test_player_season_snapshot_falls_back_to_settings_when_no_server_row(session):
    # A unit test that never calls ServerService.create_server() has no
    # Server row at all - PlayerService must still work, falling back to
    # settings.current_season_label exactly like before this feature.
    player_service = PlayerService(session, server_id=999)
    player = player_service.create_player(_player("대상"), actor_role=Role.SERVER_ADMIN)

    history = player_service.season_rank_history(player.id)
    assert history[0].season == settings.current_season_label
