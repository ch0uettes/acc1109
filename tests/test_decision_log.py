from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.balance.result import BalanceResult, FeatureContribution
from app.database.base import Base
from app.models.player import Player
from app.models.team import Team
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


def _results(players: list[Player]) -> list[BalanceResult]:
    teams = [Team(index=0, players=players[:5]), Team(index=1, players=players[5:])]
    contributions = [
        FeatureContribution(
            name="mean_balance", raw=50.0, normalized=0.2, weight=0.28, contribution=0.056, contribution_pct=100.0
        )
    ]
    good = BalanceResult(teams=teams, cost=0.1, contributions=contributions)
    worse = BalanceResult(teams=teams, cost=0.3, contributions=contributions)
    return [good, worse]


def test_log_decision_records_recommendations_and_chosen_rank(session):
    player_service = PlayerService(session, server_id=1)
    players = [player_service.create_player(_player(f"p{i}"), actor_role=Role.SERVER_ADMIN) for i in range(10)]
    signups = [PlayerSignup(player=p) for p in players]
    team_service = TeamService(session, server_id=1)
    results = _results(players)

    entry = team_service.log_decision(signups, "stable", results, chosen_rank=1)

    assert entry.id is not None
    assert entry.strategy_name == "stable"
    assert entry.player_ids == [p.id for p in players]
    assert len(entry.recommendations) == 2
    assert entry.recommendations[0].rank == 1
    assert entry.recommendations[0].cost == pytest.approx(0.1)
    assert entry.recommendations[0].contributions[0].name == "mean_balance"
    assert entry.chosen_rank == 1


def test_recent_decisions_returns_newest_first(session):
    player_service = PlayerService(session, server_id=1)
    players = [player_service.create_player(_player(f"p{i}"), actor_role=Role.SERVER_ADMIN) for i in range(10)]
    signups = [PlayerSignup(player=p) for p in players]
    team_service = TeamService(session, server_id=1)
    results = _results(players)

    team_service.log_decision(signups, "competitive", results, chosen_rank=1)
    team_service.log_decision(signups, "stable", results, chosen_rank=2, reason="포지션 만족도 우선")

    decisions = team_service.recent_decisions()
    assert len(decisions) == 2
    assert decisions[0].strategy_name == "stable"
    assert decisions[0].chosen_rank == 2
    assert decisions[0].reason == "포지션 만족도 우선"
    assert decisions[1].strategy_name == "competitive"


def test_decision_log_is_scoped_per_server(session):
    player_service = PlayerService(session, server_id=1)
    players = [player_service.create_player(_player(f"p{i}"), actor_role=Role.SERVER_ADMIN) for i in range(10)]
    signups = [PlayerSignup(player=p) for p in players]
    results = _results(players)

    TeamService(session, server_id=1).log_decision(signups, "stable", results, chosen_rank=1)

    assert TeamService(session, server_id=2).recent_decisions() == []
