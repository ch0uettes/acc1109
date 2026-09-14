from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.balance.result import BalanceResult
from app.database.base import Base
from app.models.player import Player
from app.models.team import Team
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


def _player(nickname: str, role: Position = Position.MID) -> Player:
    return Player(nickname=nickname, tier=Tier.GOLD, division=Division.I, lp=0, main_role=role)


def _save_a_run(session, players: list[Player]) -> TeamService:
    teams = [Team(index=0, players=players[:5]), Team(index=1, players=players[5:])]
    result = BalanceResult(teams=teams, cost=0.0)
    team_service = TeamService(session, server_id=1)
    team_service.save_generated_teams(result, actor_role=Role.SERVER_ADMIN)
    return team_service


def test_list_saved_runs_returns_the_most_recent_first(session):
    player_service = PlayerService(session, server_id=1)
    players = [player_service.create_player(_player(f"p{i}"), actor_role=Role.SERVER_ADMIN) for i in range(10)]
    team_service = _save_a_run(session, players)

    reordered = players[5:] + players[:5]
    team_service.save_generated_teams(
        BalanceResult(teams=[Team(index=0, players=reordered[:5]), Team(index=1, players=reordered[5:])], cost=0.0),
        actor_role=Role.SERVER_ADMIN,
    )

    runs = team_service.list_saved_runs()
    assert len(runs) == 2
    assert runs[0] > runs[1]  # most recent first


def test_load_saved_run_reproduces_the_exact_roster_and_positions(session):
    player_service = PlayerService(session, server_id=1)
    players = [
        player_service.create_player(_player(f"p{i}", role=list(Position)[i % 5]), actor_role=Role.SERVER_ADMIN)
        for i in range(10)
    ]
    team_service = _save_a_run(session, players)

    generated_at = team_service.list_saved_runs()[0]
    loaded = team_service.load_saved_run(generated_at)

    assert {t.index for t in loaded} == {0, 1}
    for team, expected_players in zip(sorted(loaded, key=lambda t: t.index), [players[:5], players[5:]]):
        assert {e.player.id for e in team.entries} == {p.id for p in expected_players}
        for entry in team.entries:
            expected = next(p for p in expected_players if p.id == entry.player.id)
            assert entry.position == expected.main_role  # Team.position_for() falls back to main_role (no slots)


def test_load_saved_run_still_shows_a_since_deactivated_participant(session):
    """Regression-guard: a player who left the server after this roster
    was saved must still show up in the reloaded roster (they were
    genuinely part of it), not silently vanish because list() defaults to
    active-only."""
    player_service = PlayerService(session, server_id=1)
    players = [player_service.create_player(_player(f"p{i}"), actor_role=Role.SERVER_ADMIN) for i in range(10)]
    team_service = _save_a_run(session, players)
    player_service.deactivate_player(players[0].id, actor_role=Role.SERVER_ADMIN)

    generated_at = team_service.list_saved_runs()[0]
    loaded = team_service.load_saved_run(generated_at)

    all_entries = [e for team in loaded for e in team.entries]
    assert any(e.player is not None and e.player.id == players[0].id for e in all_entries)


def test_load_saved_run_for_an_unknown_timestamp_returns_no_teams(session):
    from datetime import datetime

    team_service = TeamService(session, server_id=1)
    assert team_service.load_saved_run(datetime(2000, 1, 1)) == []


def test_two_saves_with_a_colliding_clock_still_get_distinct_runs(session, monkeypatch):
    """Regression test: generated_at is this server's only run identity
    (no dedicated batch table) - two save_generated_teams() calls that
    happen to land on the exact same datetime.utcnow() value (observed
    directly on a coarser system clock, e.g. Windows, when an operator
    saves two combos back to back) used to make get_run() silently merge
    both saves' rosters into a single "run", corrupting both."""
    import app.database.repositories.team_repository as team_repository_module

    player_service = PlayerService(session, server_id=1)
    players = [player_service.create_player(_player(f"p{i}"), actor_role=Role.SERVER_ADMIN) for i in range(15)]
    frozen_now = team_repository_module.datetime(2026, 1, 1, 12, 0, 0)
    monkeypatch.setattr(team_repository_module, "datetime", type("_FrozenDatetime", (), {
        "utcnow": staticmethod(lambda: frozen_now),
    }))

    team_service = TeamService(session, server_id=1)
    first = BalanceResult(teams=[Team(index=0, players=players[:5]), Team(index=1, players=players[5:10])], cost=0.0)
    second = BalanceResult(teams=[Team(index=0, players=players[10:15])], cost=0.0)
    team_service.save_generated_teams(first, actor_role=Role.SERVER_ADMIN)
    team_service.save_generated_teams(second, actor_role=Role.SERVER_ADMIN)

    runs = team_service.list_saved_runs()
    assert len(runs) == 2  # not merged into one despite the identical wall-clock reading

    rosters = [team_service.load_saved_run(run) for run in runs]
    all_player_ids_per_run = [{e.player.id for t in roster for e in t.entries} for roster in rosters]
    assert {p.id for p in players[10:15]} in all_player_ids_per_run
    assert {p.id for p in players[:10]} in all_player_ids_per_run
