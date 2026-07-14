from __future__ import annotations

import random
from abc import ABC, abstractmethod
from copy import deepcopy

from app.balance.features import BalanceEvaluator
from app.balance.result import BalanceResult
from app.models.player import Player
from app.models.team import Team
from app.utils.exceptions import InvalidPlayerCountError

TEAM_SIZE = 5


class TeamOptimizer(ABC):
    """Interface so the search strategy (random+swap now, simulated
    annealing / genetic / tabu search later) can be swapped freely."""

    @abstractmethod
    def optimize(self, players: list[Player], cost_fn: BalanceEvaluator) -> BalanceResult:
        ...


def split_into_teams(players: list[Player], rng: random.Random) -> list[Team]:
    shuffled = players[:]
    rng.shuffle(shuffled)
    num_teams = len(shuffled) // TEAM_SIZE
    return [
        Team(index=i, players=shuffled[i * TEAM_SIZE : (i + 1) * TEAM_SIZE])
        for i in range(num_teams)
    ]


class RandomSwapOptimizer(TeamOptimizer):
    """v0.1 algorithm: random initial split, then repeatedly swap one
    player between two random teams whenever it lowers cost."""

    def __init__(
        self,
        max_iterations: int = 2000,
        random_restarts: int = 10,
        seed: int | None = None,
    ) -> None:
        self.max_iterations = max_iterations
        self.random_restarts = random_restarts
        self.seed = seed

    def optimize(self, players: list[Player], cost_fn: BalanceEvaluator) -> BalanceResult:
        if len(players) == 0 or len(players) % TEAM_SIZE != 0:
            raise InvalidPlayerCountError(
                f"Player count must be a positive multiple of {TEAM_SIZE}, got {len(players)}"
            )

        rng = random.Random(self.seed)
        best_result: BalanceResult | None = None

        for _ in range(self.random_restarts):
            teams = split_into_teams(players, rng)
            cost, breakdown = cost_fn.compute(teams)

            for _ in range(self.max_iterations):
                if len(teams) < 2:
                    break
                team_a, team_b = rng.sample(teams, 2)
                idx_a = rng.randrange(len(team_a.players))
                idx_b = rng.randrange(len(team_b.players))

                team_a.players[idx_a], team_b.players[idx_b] = (
                    team_b.players[idx_b],
                    team_a.players[idx_a],
                )
                new_cost, new_breakdown = cost_fn.compute(teams)

                if new_cost < cost:
                    cost, breakdown = new_cost, new_breakdown
                else:
                    team_a.players[idx_a], team_b.players[idx_b] = (
                        team_b.players[idx_b],
                        team_a.players[idx_a],
                    )

            if best_result is None or cost < best_result.cost:
                best_result = BalanceResult(
                    teams=deepcopy(teams),
                    cost=cost,
                    cost_breakdown=breakdown,
                    iterations=self.max_iterations,
                )

        assert best_result is not None
        return best_result


class TieredSnakeDraftOptimizer(TeamOptimizer):
    """Opposite philosophy from RandomSwapOptimizer: instead of minimizing
    variance within a team, this deliberately bundles a top-rated player
    with a bottom-rated one on every team. Players are ranked by
    final_rating and cut into TEAM_SIZE tiers of num_teams players each
    (tier 0 = strongest, last tier = weakest); each team gets exactly one
    player from every tier, so every roster carries one "high" and one
    "low" alongside three mid-tier players. Snake order (forward on even
    tiers, reversed on odd tiers) spreads the residual within-tier gap
    evenly across teams instead of always favoring team 0.

    `seed`, if given, shuffles the order within each tier before the
    snake assignment - the set of players in each tier never changes,
    only which team each of them lands on, so every result still bundles
    a top-tier and bottom-tier player per team while letting the caller
    sample multiple distinct valid pairings."""

    def __init__(self, seed: int | None = None) -> None:
        self.seed = seed

    def optimize(self, players: list[Player], cost_fn: BalanceEvaluator) -> BalanceResult:
        if len(players) == 0 or len(players) % TEAM_SIZE != 0:
            raise InvalidPlayerCountError(
                f"Player count must be a positive multiple of {TEAM_SIZE}, got {len(players)}"
            )

        num_teams = len(players) // TEAM_SIZE
        ranked = sorted(players, key=lambda p: p.final_rating, reverse=True)
        rng = random.Random(self.seed)

        rosters: list[list[Player]] = [[] for _ in range(num_teams)]
        for tier_index in range(TEAM_SIZE):
            tier_group = ranked[tier_index * num_teams : (tier_index + 1) * num_teams]
            if self.seed is not None:
                tier_group = tier_group[:]
                rng.shuffle(tier_group)
            team_order = range(num_teams) if tier_index % 2 == 0 else range(num_teams - 1, -1, -1)
            for team_index, player in zip(team_order, tier_group):
                rosters[team_index].append(player)

        teams = [Team(index=i, players=rosters[i]) for i in range(num_teams)]
        cost, breakdown = cost_fn.compute(teams)
        return BalanceResult(teams=teams, cost=cost, cost_breakdown=breakdown, iterations=0)
