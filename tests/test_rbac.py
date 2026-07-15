from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.base import Base
from app.models.player import Player
from app.models.team import Team
from app.balance.result import BalanceResult
from app.services.match_service import MatchService
from app.services.player_service import PlayerService
from app.services.rbac import Permission, has_permission
from app.services.server_service import ServerService
from app.services.team_service import TeamService
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


def _player(nickname: str) -> Player:
    return Player(nickname=nickname, tier=Tier.GOLD, division=Division.I, lp=0, main_role=Position.MID)


def test_owner_permissions_are_a_superset_of_server_admin():
    for permission in Permission:
        if has_permission(Role.SERVER_ADMIN, permission):
            assert has_permission(Role.OWNER, permission)


def test_player_has_no_admin_permissions():
    assert not has_permission(Role.PLAYER, Permission.MANAGE_PLAYERS)
    assert not has_permission(Role.PLAYER, Permission.SET_SEED_RATING)
    assert not has_permission(Role.PLAYER, Permission.CREATE_MATCH)


def test_create_server_grants_owner_and_logs_audit(session):
    service = ServerService(session)

    server = service.create_server("테스트 서버", owner_display_name="홍길동")

    members = service.list_members(server.id)
    assert len(members) == 1
    assert members[0].display_name == "홍길동"
    assert members[0].role == Role.OWNER

    history = service.role_change_history(server.id)
    assert len(history) == 1
    assert history[0].old_role is None
    assert history[0].new_role == Role.OWNER
    assert history[0].changed_by == "홍길동"


def test_server_admin_can_promote_a_player_to_server_admin(session):
    service = ServerService(session)
    server = service.create_server("서버", owner_display_name="Owner1")
    service.promote_to_server_admin(server.id, "Owner1", "Admin1")

    promoted = service.promote_to_server_admin(server.id, "Admin1", "이경훈", reason="내전 운영 담당")

    assert promoted.role == Role.SERVER_ADMIN
    history = service.role_change_history(server.id)
    latest = history[-1]
    assert latest.target_display_name == "이경훈"
    assert latest.old_role == Role.PLAYER
    assert latest.new_role == Role.SERVER_ADMIN
    assert latest.changed_by == "Admin1"
    assert latest.reason == "내전 운영 담당"


def test_plain_player_cannot_promote(session):
    service = ServerService(session)
    server = service.create_server("서버", owner_display_name="Owner1")
    service.add_player_member(server.id, "일반유저")

    with pytest.raises(PermissionDeniedError):
        service.promote_to_server_admin(server.id, "일반유저", "다른유저")


def test_only_owner_can_remove_server_admin(session):
    service = ServerService(session)
    server = service.create_server("서버", owner_display_name="Owner1")
    service.promote_to_server_admin(server.id, "Owner1", "Admin1")
    service.promote_to_server_admin(server.id, "Owner1", "Admin2")

    with pytest.raises(PermissionDeniedError):
        service.remove_server_admin(server.id, "Admin1", "Admin2")

    demoted = service.remove_server_admin(server.id, "Owner1", "Admin2", reason="활동 없음")
    assert demoted.role == Role.PLAYER


def test_transfer_ownership_demotes_old_owner_to_server_admin(session):
    service = ServerService(session)
    server = service.create_server("서버", owner_display_name="Owner1")
    service.add_player_member(server.id, "NewOwner")

    new_owner = service.transfer_ownership(server.id, "Owner1", "NewOwner", reason="은퇴")

    assert new_owner.role == Role.OWNER
    old_owner = service.get_member(server.id, "Owner1")
    assert old_owner.role == Role.SERVER_ADMIN

    with pytest.raises(PermissionDeniedError):
        service.transfer_ownership(server.id, "Owner1", "NewOwner")


def test_player_role_cannot_create_player(session):
    service = PlayerService(session, server_id=1)

    with pytest.raises(PermissionDeniedError):
        service.create_player(_player("누군가"), actor_role=Role.PLAYER)


def test_player_role_cannot_set_seed_rating(session):
    service = PlayerService(session, server_id=1)
    created = service.create_player(_player("대상"), actor_role=Role.SERVER_ADMIN)

    with pytest.raises(PermissionDeniedError):
        service.set_seed_rating(created.id, Tier.GOLD, changed_by="누군가", actor_role=Role.PLAYER)


def test_player_role_cannot_override_internal_rating(session):
    service = PlayerService(session, server_id=1)
    created = service.create_player(_player("대상"), actor_role=Role.SERVER_ADMIN)

    with pytest.raises(PermissionDeniedError):
        service.override_internal_rating(created.id, 999.0, actor_role=Role.PLAYER)

    updated = service.override_internal_rating(created.id, 999.0, actor_role=Role.SERVER_ADMIN)
    assert updated.internal_rating == 999.0


def test_player_role_cannot_record_match(session):
    player_service = PlayerService(session, server_id=1)
    players = [
        player_service.create_player(_player(f"p{i}"), actor_role=Role.SERVER_ADMIN) for i in range(10)
    ]
    teams = [Team(index=0, players=players[:5]), Team(index=1, players=players[5:])]
    match_service = MatchService(session, server_id=1)

    with pytest.raises(PermissionDeniedError):
        match_service.record_match(teams, winning_team_index=0, actor_role=Role.PLAYER)


def test_player_role_cannot_save_generated_teams(session):
    # save_generated_teams() writes rosters to the DB - same permission
    # tier as record_match(), not a base-level action every Player gets.
    player_service = PlayerService(session, server_id=1)
    players = [
        player_service.create_player(_player(f"p{i}"), actor_role=Role.SERVER_ADMIN) for i in range(10)
    ]
    teams = [Team(index=0, players=players[:5]), Team(index=1, players=players[5:])]
    result = BalanceResult(teams=teams, cost=0.0)
    team_service = TeamService(session, server_id=1)

    with pytest.raises(PermissionDeniedError):
        team_service.save_generated_teams(result, actor_role=Role.PLAYER)

    saved_ids = team_service.save_generated_teams(result, actor_role=Role.SERVER_ADMIN)
    assert len(saved_ids) == 2
