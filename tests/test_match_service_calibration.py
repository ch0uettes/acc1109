from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.base import Base
from app.models.player import Player
from app.models.team import Team, TeamSlot
from app.services.match_service import MatchService
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


def _make_full_teams(player_service: PlayerService) -> list[Team]:
    players = []
    for i in range(10):
        p = player_service.create_player(
            Player(nickname=f"p{i}", tier=Tier.GOLD, division=Division.I, lp=0, main_role=Position.MID),
            actor_role=Role.SERVER_ADMIN,
        )
        players.append(p)
    return [Team(index=0, players=players[:5]), Team(index=1, players=players[5:])]


def test_calibration_mode_exits_after_threshold_games(session):
    player_service = PlayerService(session, server_id=1)
    teams = _make_full_teams(player_service)

    calibration_player_id = teams[0].players[0].id
    player_service.repo.update(
        player_service.get_player(calibration_player_id).model_copy(update={"calibration_mode": True})
    )

    match_service = MatchService(session, server_id=1)
    for _ in range(5):
        refreshed_teams = [
            Team(index=t.index, players=[player_service.get_player(p.id) for p in t.players])
            for t in teams
        ]
        match_service.record_match(refreshed_teams, winning_team_index=0, actor_role=Role.SERVER_ADMIN)

    final_player = player_service.get_player(calibration_player_id)
    assert final_player.games_played == 5
    assert final_player.calibration_mode is False


def test_recorded_position_reflects_slot_assignment_not_profile_main_role(session):
    player_service = PlayerService(session, server_id=1)
    teams = _make_full_teams(player_service)
    team0, team1 = teams

    slotted_player = team0.players[0]
    other_players = team0.players[1:]
    slots = [TeamSlot(position=Position.TOP, player=slotted_player, role_penalty=10.0, role_source="sub")] + [
        TeamSlot(position=pos, player=p, role_penalty=0.0, role_source="main")
        for pos, p in zip([Position.JUNGLE, Position.MID, Position.ADC, Position.SUPPORT], other_players)
    ]
    team0_with_slots = Team(index=0, players=team0.players, slots=slots)

    match_service = MatchService(session, server_id=1)
    match = match_service.record_match(
        [team0_with_slots, team1], winning_team_index=0, actor_role=Role.SERVER_ADMIN
    )

    recorded = next(p for p in match.participants if p.player_id == slotted_player.id)
    assert recorded.position == Position.TOP
    assert recorded.position != slotted_player.main_role
