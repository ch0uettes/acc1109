from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.base import Base
from app.models.player import Player
from app.models.team import Team
from app.services.match_service import MatchService
from app.services.player_service import PlayerService
from app.services.server_service import ServerService
from app.utils.enums import Division, Position, Role, Tier
from app.utils.exceptions import PermissionDeniedError


@pytest.fixture
def session():
    from app.database import entities  # noqa: F401  registers tables on Base.metadata

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    with SessionLocal() as s:
        yield s


def _player(nickname: str, role: Position = Position.MID) -> Player:
    return Player(nickname=nickname, tier=Tier.GOLD, division=Division.I, lp=0, main_role=role)


@pytest.fixture
def server_and_service(session):
    server = ServerService(session).create_server("테스트 서버", owner_display_name="운영자")
    return server, PlayerService(session, server_id=server.id)


def test_new_player_defaults_to_active(server_and_service):
    _, service = server_and_service
    player = service.create_player(_player("대상"), actor_role=Role.SERVER_ADMIN)
    assert player.is_active is True
    assert player in service.list_players()


def test_deactivate_removes_player_from_default_list(server_and_service):
    _, service = server_and_service
    player = service.create_player(_player("대상"), actor_role=Role.SERVER_ADMIN)

    service.deactivate_player(player.id, actor_role=Role.SERVER_ADMIN)

    assert player.id not in {p.id for p in service.list_players()}


def test_deactivate_keeps_the_row_queryable_with_include_inactive(server_and_service):
    _, service = server_and_service
    player = service.create_player(_player("대상"), actor_role=Role.SERVER_ADMIN)

    service.deactivate_player(player.id, actor_role=Role.SERVER_ADMIN)

    still_there = service.list_players(include_inactive=True)
    assert player.id in {p.id for p in still_there}
    assert service.get_player(player.id).nickname == "대상"


def test_reactivate_brings_the_player_back(server_and_service):
    _, service = server_and_service
    player = service.create_player(_player("대상"), actor_role=Role.SERVER_ADMIN)
    service.deactivate_player(player.id, actor_role=Role.SERVER_ADMIN)

    service.reactivate_player(player.id, actor_role=Role.SERVER_ADMIN)

    assert player.id in {p.id for p in service.list_players()}


def test_deactivate_requires_manage_players_permission(server_and_service):
    _, service = server_and_service
    player = service.create_player(_player("대상"), actor_role=Role.SERVER_ADMIN)

    with pytest.raises(PermissionDeniedError):
        service.deactivate_player(player.id, actor_role=Role.PLAYER)


def test_deactivating_a_player_with_match_history_does_not_raise(session, server_and_service):
    """The bug this whole feature replaces: a hard DELETE on a player who
    has ever played a match either orphans FK rows (SQLite, no FK
    enforcement) or raises an uncaught IntegrityError (real Postgres).
    Deactivating must work cleanly regardless of history."""
    server, service = server_and_service
    players = [service.create_player(_player(f"p{i}"), actor_role=Role.SERVER_ADMIN) for i in range(5)]

    match_service = MatchService(session, server_id=server.id)
    team = Team(index=0, players=players, slots=None)
    match_service.record_match(teams=[team], winning_team_index=0, actor_role=Role.SERVER_ADMIN)

    # Must not raise, unlike the old hard-delete path.
    service.deactivate_player(players[0].id, actor_role=Role.SERVER_ADMIN)

    assert players[0].id not in {p.id for p in service.list_players()}
    # The match's own record of who played is untouched.
    recorded_match = match_service.match_repo.list()[0]
    assert players[0].id in {p.player_id for p in recorded_match.participants}
