from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.base import Base
from app.models.player import Player
from app.rating.resolver import CONFIDENCE_MANUAL
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


def test_create_player_applies_the_manual_confidence_band(session):
    """Regression test: create_player() (the '수동 입력' manual-entry path)
    used to leave confidence at Player's bare pydantic default (0.5)
    instead of CONFIDENCE_MANUAL (0.85) - the band RatingCaseResolver.
    resolve_manual() documents for this exact case ("an operator directly
    entering an exact tier they know to be true"), silently under-weighting
    every manually-added player's rating in confidence-weighted balancing."""
    service = PlayerService(session, server_id=1)

    player = service.create_player(
        Player(
            nickname="수동입력유저",
            tier=Tier.GOLD,
            division=Division.II,
            lp=40,
            main_role=Position.MID,
        ),
        actor_role=Role.SERVER_ADMIN,
    )

    assert player.confidence == pytest.approx(CONFIDENCE_MANUAL)
