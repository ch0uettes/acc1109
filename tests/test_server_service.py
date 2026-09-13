from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.base import Base
from app.services.server_service import ServerService
from app.utils.enums import Role
from app.utils.exceptions import DuplicateMembershipError, DuplicateServerError


@pytest.fixture
def session():
    from app.database import entities  # noqa: F401  registers tables on Base.metadata

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    with SessionLocal() as s:
        yield s


def test_add_player_member_is_idempotent_for_the_same_name(session):
    service = ServerService(session)
    server = service.create_server("서버", owner_display_name="Owner")

    first = service.add_player_member(server.id, "홍길동")
    second = service.add_player_member(server.id, "홍길동")

    assert first.id == second.id
    assert len(service.list_members(server.id)) == 2  # Owner + 홍길동, not a duplicate row


def test_add_player_member_survives_a_race_past_the_precheck(session, monkeypatch):
    """Regression test: the same crash class already fixed for duplicate
    player nicknames (an uncaught IntegrityError that also leaves the
    session's transaction unusable) previously applied here too. Simulates
    two near-simultaneous self-registrations of the same name by forcing
    the existence precheck to report "not found" right before the second
    insert - the unique constraint on (server_id, display_name) must still
    stop the duplicate row, and the service must recover gracefully rather
    than crash or leave the session broken."""
    service = ServerService(session)
    server = service.create_server("서버", owner_display_name="Owner")
    existing = service.add_player_member(server.id, "홍길동")

    # First call (the precheck before insert) reports "not found", forcing
    # the insert attempt that collides with the unique constraint; the
    # second call (this method's own post-rollback recheck) sees the real,
    # already-committed row - exactly what a resolved race looks like.
    original_get_member = service.get_member
    calls = {"n": 0}

    def flaky_get_member(server_id, display_name):
        calls["n"] += 1
        return None if calls["n"] == 1 else original_get_member(server_id, display_name)

    monkeypatch.setattr(service, "get_member", flaky_get_member)

    result = service.add_player_member(server.id, "홍길동")

    # the rollback-and-recheck path finds the winner's row instead of
    # raising, since self-registration is meant to be idempotent
    assert result.id == existing.id
    # the session must still be usable afterwards (rollback happened)
    assert len(service.list_members(server.id)) == 2


def test_duplicate_discord_guild_id_raises_domain_error_not_a_raw_integrity_error(session):
    service = ServerService(session)
    service.create_server("서버 A", owner_display_name="OwnerA", discord_guild_id="guild-1")

    with pytest.raises(DuplicateServerError):
        service.create_server("서버 B", owner_display_name="OwnerB", discord_guild_id="guild-1")

    # the session must still be usable afterwards (rollback happened)
    assert len(service.list_servers()) == 1
