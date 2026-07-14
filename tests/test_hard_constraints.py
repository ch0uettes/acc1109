from __future__ import annotations

from app.balance.config import HardConstraintConfig
from app.balance.constraints import HardConstraintLayer
from app.models.player import Player
from app.models.team import Team, TeamSlot
from app.utils.enums import Position, Tier


def _player(rating: float = 100.0) -> Player:
    return Player(nickname="p", tier=Tier.GOLD, main_role=Position.MID, official_rating=rating)


def _slot(player: Player, position: Position, role_source: str = "main") -> TeamSlot:
    return TeamSlot(position=position, player=player, role_penalty=0.0, role_source=role_source)


def _full_team(index: int, role_source: str = "main") -> Team:
    players = [_player() for _ in range(5)]
    slots = [_slot(p, pos, role_source) for p, pos in zip(players, Position)]
    return Team(index=index, players=players, slots=slots)


def test_default_config_never_rejects_a_structurally_valid_candidate():
    # Permissive by default (see HardConstraintConfig docstring) - Soft
    # Penalty, not Hard Constraint, is the primary fairness lever.
    layer = HardConstraintLayer()
    teams = [_full_team(0), _full_team(1)]
    raw_breakdown = {"average_rating": 999_999.0, "lane_balance": 999_999.0, "team_variance": 999_999.0}
    assert layer.is_feasible(teams, raw_breakdown) is True


def test_rejects_a_team_with_the_wrong_player_count():
    layer = HardConstraintLayer()
    malformed = Team(index=0, players=[_player(), _player()])  # only 2, not 5
    teams = [malformed, _full_team(1)]
    assert layer.is_feasible(teams, {}) is False


def test_rejects_a_team_missing_a_position_slot():
    layer = HardConstraintLayer()
    players = [_player() for _ in range(5)]
    # Two players both assigned TOP, none assigned SUPPORT - structurally invalid.
    slots = [_slot(players[0], Position.TOP), _slot(players[1], Position.TOP)] + [
        _slot(p, pos) for p, pos in zip(players[2:], [Position.JUNGLE, Position.MID, Position.ADC])
    ]
    malformed = Team(index=0, players=players, slots=slots)
    teams = [malformed, _full_team(1)]
    assert layer.is_feasible(teams, {}) is False


def test_configured_average_rating_threshold_rejects_over_the_limit():
    layer = HardConstraintLayer(HardConstraintConfig(average_rating_diff_max=500.0))
    teams = [_full_team(0), _full_team(1)]
    assert layer.is_feasible(teams, {"average_rating": 501.0}) is False
    assert layer.is_feasible(teams, {"average_rating": 500.0}) is True


def test_configured_minimum_main_role_ratio_rejects_below_the_floor():
    layer = HardConstraintLayer(HardConstraintConfig(minimum_main_role_ratio=0.6))
    mostly_other = [_full_team(0, role_source="other"), _full_team(1, role_source="main")]
    # 5 "main" out of 10 total slots = 0.5 ratio, below the 0.6 floor.
    assert layer.is_feasible(mostly_other, {}) is False

    mostly_main = [_full_team(0, role_source="main"), _full_team(1, role_source="main")]
    assert layer.is_feasible(mostly_main, {}) is True
