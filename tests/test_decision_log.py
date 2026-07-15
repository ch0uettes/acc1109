from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.base import Base
from app.database.entities.decision_log import DecisionLogEntity
from app.models.player import Player
from app.position.signup import PlayerSignup
from app.services.player_service import PlayerService
from app.services.team_service import TeamService
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


def test_log_decision_records_execution_context_and_chosen_rank(session):
    player_service = PlayerService(session, server_id=1)
    players = [player_service.create_player(_player(f"p{i}"), actor_role=Role.SERVER_ADMIN) for i in range(10)]
    signups = [PlayerSignup(player=p) for p in players]
    team_service = TeamService(session, server_id=1)

    context = team_service.run(signups, k=3)
    entry = team_service.log_decision(context, chosen_rank=1)

    assert entry.id is not None
    assert entry.execution_id == context.input.execution_id
    assert entry.strategy_name == context.input.strategy.name
    assert entry.search_policy_name == context.input.search_policy.name
    assert entry.player_ids == [p.id for p in players]
    assert len(entry.player_snapshot) == 10
    assert entry.player_snapshot[0].nickname == "p0"
    assert entry.search_statistics is not None
    assert entry.search_statistics.nodes_expanded > 0
    assert entry.version_metadata is not None
    assert entry.version_metadata.app_version
    assert entry.candidate_count == len(context.runtime.candidate_teams)
    assert entry.execution_time_seconds is not None
    assert len(entry.recommendations) == len(context.runtime.candidate_teams)
    assert entry.recommendations[0].rank == 1
    assert entry.chosen_rank == 1


def test_recent_decisions_returns_newest_first(session):
    player_service = PlayerService(session, server_id=1)
    players = [player_service.create_player(_player(f"p{i}"), actor_role=Role.SERVER_ADMIN) for i in range(10)]
    signups = [PlayerSignup(player=p) for p in players]
    team_service = TeamService(session, server_id=1)

    context1 = team_service.run(signups, k=3)
    team_service.log_decision(context1, chosen_rank=1)
    context2 = team_service.run(signups, k=3)
    team_service.log_decision(context2, chosen_rank=2, reason="포지션 만족도 우선")

    decisions = team_service.recent_decisions()
    assert len(decisions) == 2
    assert decisions[0].chosen_rank == 2
    assert decisions[0].reason == "포지션 만족도 우선"
    assert decisions[1].chosen_rank == 1


def test_decision_log_is_scoped_per_server(session):
    player_service = PlayerService(session, server_id=1)
    players = [player_service.create_player(_player(f"p{i}"), actor_role=Role.SERVER_ADMIN) for i in range(10)]
    signups = [PlayerSignup(player=p) for p in players]

    context = TeamService(session, server_id=1).run(signups, k=3)
    TeamService(session, server_id=1).log_decision(context, chosen_rank=1)

    assert TeamService(session, server_id=2).recent_decisions() == []


def test_decision_log_repository_tolerates_pre_v1_rows_with_no_new_columns(session):
    # Rows written before this schema expansion have NULL in every new
    # column at the DB level, not just a missing JSON key - the
    # repository must not crash reading them.
    entity = DecisionLogEntity(
        server_id=1,
        strategy_name="stable",
        player_ids=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
        recommendations=[
            {
                "rank": 1,
                "cost": 0.1,
                "team_player_ids": [[1, 2, 3, 4, 5], [6, 7, 8, 9, 10]],
                "contributions": [],
            }
        ],
        chosen_rank=1,
    )
    session.add(entity)
    session.commit()

    decisions = TeamService(session, server_id=1).recent_decisions()

    assert len(decisions) == 1
    entry = decisions[0]
    assert entry.execution_id is None
    assert entry.search_policy_name is None
    assert entry.player_snapshot == []
    assert entry.search_statistics is None
    assert entry.version_metadata is None
    assert entry.execution_time_seconds is None
    assert entry.candidate_count is None
    assert entry.chosen_rank == 1
