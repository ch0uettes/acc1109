from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.balance.config import (
    DEFAULT_HARD_CONSTRAINT_CONFIG,
    DEFAULT_NORMALIZATION_CONFIG,
    HardConstraintConfig,
    NormalizationConfig,
)
from app.database.base import Base
from app.services.server_service import ServerService
from app.utils.exceptions import PermissionDeniedError


@pytest.fixture
def session():
    from app.database import entities  # noqa: F401  registers tables on Base.metadata

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    with SessionLocal() as s:
        yield s


def test_new_server_defaults_to_the_module_level_balance_config(session):
    service = ServerService(session)
    server = service.create_server("테스트 서버", owner_display_name="홍길동")

    assert server.normalization_config == DEFAULT_NORMALIZATION_CONFIG
    assert server.hard_constraint_config == DEFAULT_HARD_CONSTRAINT_CONFIG


def test_owner_can_update_and_reload_balance_config(session):
    service = ServerService(session)
    server = service.create_server("테스트 서버", owner_display_name="홍길동")

    normalization = NormalizationConfig(
        average_rating_midpoint=300.0,
        average_rating_steepness=0.01,
        internal_rating_midpoint=300.0,
        internal_rating_steepness=0.01,
        lane_difference_max=4000.0,
        team_variance_scale=100_000.0,
        tier_distribution_breakpoints=((0.0, 0.0), (3.0, 0.5), (10.0, 1.0)),
        role_penalty_max=800.0,
    )
    hard_constraint = HardConstraintConfig(
        average_rating_diff_max=900.0,
        lane_diff_max=None,
        team_variance_max=None,
        minimum_main_role_ratio=0.5,
    )

    updated = service.update_balance_config(server.id, "홍길동", normalization, hard_constraint)
    assert updated.normalization_config == normalization
    assert updated.hard_constraint_config == hard_constraint

    # Round-trips correctly through the DB, not just the in-memory return value.
    reloaded = service.get_server(server.id)
    assert reloaded.normalization_config == normalization
    assert reloaded.hard_constraint_config == hard_constraint


def test_non_owner_cannot_update_balance_config(session):
    service = ServerService(session)
    server = service.create_server("테스트 서버", owner_display_name="홍길동")
    service.add_player_member(server.id, "일반유저")

    with pytest.raises(PermissionDeniedError):
        service.update_balance_config(
            server.id, "일반유저", NormalizationConfig(), HardConstraintConfig()
        )
