from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.base import Base
from app.models.player import Player
from app.services.player_service import PlayerService
from app.utils.enums import Division, Position, Role, Tier
from app.utils.exceptions import InvalidRatingValueError, PermissionDeniedError


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


def test_internal_rating_override_is_audited_with_old_and_new_value(session):
    service = PlayerService(session, server_id=1)
    player = service.create_player(_player("대상"), actor_role=Role.SERVER_ADMIN)

    updated = service.override_internal_rating(
        player.id, 250.0, actor_role=Role.SERVER_ADMIN, changed_by="admin_alice", reason="캘리브레이션 오류 보정"
    )

    assert updated.internal_rating == 250.0
    history = service.internal_rating_history(player.id)
    assert len(history) == 1
    assert history[0].old_internal_rating == 0.0
    assert history[0].new_internal_rating == 250.0
    assert history[0].changed_by == "admin_alice"
    assert history[0].reason == "캘리브레이션 오류 보정"


def test_internal_rating_override_negative_value_is_allowed(session):
    # internal_rating is a relative correction, not an absolute rank - a
    # player judged much weaker than their auto-computed value can
    # legitimately have a negative override.
    service = PlayerService(session, server_id=1)
    player = service.create_player(_player("대상"), actor_role=Role.SERVER_ADMIN)

    updated = service.override_internal_rating(
        player.id, -150.0, actor_role=Role.SERVER_ADMIN, changed_by="admin_alice"
    )

    assert updated.internal_rating == -150.0


def test_internal_rating_override_rejects_implausibly_large_magnitude(session):
    service = PlayerService(session, server_id=1)
    player = service.create_player(_player("대상"), actor_role=Role.SERVER_ADMIN)

    with pytest.raises(InvalidRatingValueError):
        service.override_internal_rating(player.id, 5000.0, actor_role=Role.SERVER_ADMIN, changed_by="admin_alice")

    with pytest.raises(InvalidRatingValueError):
        service.override_internal_rating(player.id, -5000.0, actor_role=Role.SERVER_ADMIN, changed_by="admin_alice")

    assert service.internal_rating_history(player.id) == []


def test_internal_rating_override_requires_permission(session):
    service = PlayerService(session, server_id=1)
    player = service.create_player(_player("대상"), actor_role=Role.SERVER_ADMIN)

    with pytest.raises(PermissionDeniedError):
        service.override_internal_rating(player.id, 100.0, actor_role=Role.PLAYER, changed_by="누군가")

    assert service.internal_rating_history(player.id) == []
