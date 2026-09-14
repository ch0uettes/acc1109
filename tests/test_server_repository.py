from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.balance.config import DEFAULT_HARD_CONSTRAINT_CONFIG, DEFAULT_NORMALIZATION_CONFIG
from app.database.base import Base
from app.database.repositories.server_repository import ServerRepository


@pytest.fixture
def session():
    from app.database import entities  # noqa: F401  registers tables on Base.metadata

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    with SessionLocal() as s:
        yield s


def test_update_balance_config_on_a_missing_server_raises_a_clean_error(session):
    """Regression test: every other repository's update methods
    (PlayerRepository, ServerMembershipRepository) check for a missing
    entity and raise a domain error - these three didn't, so a stale or
    deleted server_id used to crash with a raw
    AttributeError('NoneType' object has no attribute ...) instead."""
    repo = ServerRepository(session)
    with pytest.raises(ValueError):
        repo.update_balance_config(999, DEFAULT_NORMALIZATION_CONFIG, DEFAULT_HARD_CONSTRAINT_CONFIG)


def test_update_season_label_on_a_missing_server_raises_a_clean_error(session):
    repo = ServerRepository(session)
    with pytest.raises(ValueError):
        repo.update_season_label(999, "S2026")


def test_update_constraint_priorities_on_a_missing_server_raises_a_clean_error(session):
    repo = ServerRepository(session)
    with pytest.raises(ValueError):
        repo.update_constraint_priorities(999, {"fixed_role": 90})
