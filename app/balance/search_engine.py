from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Optional

from app.balance.config import DEFAULT_NORMALIZATION_CONFIG, NormalizationConfig
from app.balance.constraints import HardConstraintLayer
from app.balance.features import DEFAULT_FEATURE_REGISTRY, BalanceEvaluator, FeatureRegistry
from app.balance.result import BalanceResult
from app.balance.strategy import DEFAULT_STRATEGY, IBalanceStrategy
from app.models.player import Player
from app.models.team import Team
from app.position.assigner import BipartiteMatchingPositionAssigner, PositionAssigner
from app.position.schemas import RolePreference
from app.utils.exceptions import InvalidPlayerCountError

TEAM_SIZE = 5


class TeamSearchEngine(ABC):
    """Explores candidate team-membership + position-assignment
    combinations, scores each via a BalanceEvaluator, returns the best.
    Doesn't know how `preferences` were resolved (TeamBalancer/
    RolePreferenceManager's job) or how BalanceEvaluator computes its
    score internally - only that lower is better. Swappable: Beam Search /
    Genetic Algorithm / Simulated Annealing / Branch and Bound can all
    implement this same one-method interface later."""

    @abstractmethod
    def search(self, players: list[Player], preferences: dict[int, RolePreference]) -> BalanceResult:
        ...

    def search_top_k(
        self, players: list[Player], preferences: dict[int, RolePreference], k: int = 3
    ) -> list[BalanceResult]:
        """Default fallback for engines that don't natively explore
        multiple distinct candidates: just wraps search() as a
        single-item list. BacktrackingSearchEngine overrides this with a
        real top-k implementation; a future Beam Search engine, whose
        whole approach is "keep a beam of candidates," would too."""
        return [self.search(players, preferences)]


def _team_membership_signature(teams: list[Team]) -> frozenset:
    """Identity of a team-membership partition, independent of team
    index/labeling or position assignment - two results with the same
    5 players on each side are "the same combination" even if the
    lane/other-penalty details differ slightly."""
    return frozenset(frozenset(p.id for p in team.players) for team in teams)


class _TopKResults:
    """Keeps the best `k` *distinct* team-membership partitions seen so
    far, sorted ascending by cost. Distinctness is what makes "top 3"
    meaningful - without deduping by membership, the same near-optimal
    partition could occupy all 3 slots with only cosmetic differences."""

    def __init__(self, k: int) -> None:
        self.k = k
        self._results: list[BalanceResult] = []

    def offer(self, candidate: BalanceResult) -> None:
        signature = _team_membership_signature(candidate.teams)
        for i, existing in enumerate(self._results):
            if _team_membership_signature(existing.teams) == signature:
                if candidate.cost < existing.cost:
                    self._results[i] = candidate
                    self._results.sort(key=lambda r: r.cost)
                return
        self._results.append(candidate)
        self._results.sort(key=lambda r: r.cost)
        del self._results[self.k :]

    def results(self) -> list[BalanceResult]:
        return list(self._results)


def _filter_by_quality(results: list[BalanceResult], max_cost_ratio: float) -> list[BalanceResult]:
    """Keeps the best result always, and any additional result only if its
    cost isn't wildly worse than the best (cost <= best_cost * max_cost_ratio).

    Without this, "top 3" can include a badly lopsided split (e.g. every
    top-rated player stacked onto one team) purely because it's the
    *least-bad* of whatever else the budgeted DFS happened to explore -
    "2위"/"3위" would then mislead an operator into thinking they're
    comparably fair alternatives to 1위, when the cost gap says otherwise.
    Better to honestly show fewer than k combos (same graceful-degradation
    idea as the max_nodes/dedup logic above) than a dishonest-looking one."""
    if not results:
        return results
    best_cost = results[0].cost
    if best_cost <= 0:
        return [r for r in results if r.cost <= 0] or results[:1]
    return [results[0]] + [r for r in results[1:] if r.cost <= best_cost * max_cost_ratio]


class BacktrackingSearchEngine(TeamSearchEngine):
    """v1 search algorithm. True exhaustive brute force is infeasible at
    this scale (20 players into 4 labeled teams of 5 is ~11.7 billion raw
    partitions), so this is a budgeted, warm-started DFS - NOT a
    global-optimum guarantee, just a good-effort search within a node/time
    budget that always returns a valid, fully-evaluated result.

    - Players are processed one at a time, sorted descending by
      final_rating (tightens the search early, gives deterministic output).
    - Branches over which not-yet-full team to place the current player
      in - branching factor is num_teams, not the full partition count.
    - Symmetry-broken: never opens team t+1 before team t has >=1 player,
      so equivalent partitions under team-index relabeling aren't
      re-explored num_teams! times over.
    - Warm-started with one greedy snake-draft partition (same idea as
      TieredSnakeDraftOptimizer) evaluated *before* DFS starts, so a
      valid result exists even under an ungenerous budget.
    - Hard-capped by `max_nodes` (leaf evaluations) and
      `time_budget_seconds`; whichever is hit first stops the search.
    - `search_top_k()` tracks the best K *distinct* partitions found
      during the same single DFS pass (no extra search cost) instead of
      only the single best.

    Every leaf goes through HardConstraintLayer.is_feasible() before it's
    eligible for top-K; see app/balance/constraints.py for why that layer
    is a Feasibility Check (mostly structural, numeric thresholds off by
    default), not the primary fairness mechanism - that's BalanceEvaluator's
    normalized + weighted Soft Penalty scoring.
    """

    def __init__(
        self,
        position_assigner: Optional[PositionAssigner] = None,
        evaluator: Optional[BalanceEvaluator] = None,
        strategy: Optional[IBalanceStrategy] = None,
        feature_registry: Optional[FeatureRegistry] = None,
        hard_constraints: Optional[HardConstraintLayer] = None,
        normalization_config: Optional[NormalizationConfig] = None,
        max_nodes: int = 20_000,
        time_budget_seconds: float = 5.0,
        max_cost_ratio: float = 1.25,
    ) -> None:
        """Normal usage: pick `strategy` (Competitive/Comfort/Stable,
        default Stable Mode) and nothing else - the Features to run come
        from `feature_registry.get_active_features(strategy, normalization_config)`
        fresh on every search, so this class never hardcodes which
        Features exist or how many. `normalization_config` is typically a
        Server's saved override (see app/models/server.py); defaults to
        the code-level DEFAULT_NORMALIZATION_CONFIG when not given.
        `max_cost_ratio` bounds how much worse a 2nd/3rd-place combo is
        allowed to be relative to the 1st-place cost before search_top_k()
        drops it instead of showing a misleadingly bad "alternative" (see
        _filter_by_quality). `evaluator`/`feature_registry`/
        `hard_constraints` are only for tests/advanced callers who want to
        swap a piece independently."""
        self.position_assigner = position_assigner or BipartiteMatchingPositionAssigner()
        self.evaluator = evaluator or BalanceEvaluator()
        self.strategy = strategy or DEFAULT_STRATEGY
        self.feature_registry = feature_registry or DEFAULT_FEATURE_REGISTRY
        self.hard_constraints = hard_constraints or HardConstraintLayer()
        self.normalization_config = normalization_config or DEFAULT_NORMALIZATION_CONFIG
        self.max_nodes = max_nodes
        self.time_budget_seconds = time_budget_seconds
        self.max_cost_ratio = max_cost_ratio

    def search(self, players: list[Player], preferences: dict[int, RolePreference]) -> BalanceResult:
        return self.search_top_k(players, preferences, k=1)[0]

    def search_top_k(
        self, players: list[Player], preferences: dict[int, RolePreference], k: int = 3
    ) -> list[BalanceResult]:
        if len(players) == 0 or len(players) % TEAM_SIZE != 0:
            raise InvalidPlayerCountError(
                f"Player count must be a positive multiple of {TEAM_SIZE}, got {len(players)}"
            )

        num_teams = len(players) // TEAM_SIZE
        ordered = sorted(players, key=lambda p: p.final_rating, reverse=True)
        features = self.feature_registry.get_active_features(self.strategy, self.normalization_config)
        top = _TopKResults(k)

        def evaluate_and_offer(teams: list[Team]) -> BalanceResult:
            raw = self.evaluator.evaluate_raw(teams, features)
            normalized = self.evaluator.normalize(raw, features)
            cost = self.evaluator.combine(normalized, self.strategy)
            result = BalanceResult(teams=teams, cost=cost, cost_breakdown=raw, iterations=0)
            if self.hard_constraints.is_feasible(teams, raw):
                top.offer(result)
            return result

        warm_start_result = evaluate_and_offer(self._build_warm_start_teams(ordered, num_teams, preferences))

        self._nodes_expanded = 0
        deadline = time.monotonic() + self.time_budget_seconds
        rosters: list[list[Player]] = [[] for _ in range(num_teams)]
        self._dfs(ordered, 0, rosters, num_teams, preferences, evaluate_and_offer, deadline)

        results = top.results()
        if not results:
            # Only reachable when HardConstraintConfig has been tightened
            # so strictly that nothing explored satisfies it - guarantee
            # a valid, fully-evaluated result regardless (see class
            # docstring's warm-start guarantee).
            results = [warm_start_result]
        else:
            results = _filter_by_quality(results, self.max_cost_ratio)

        # explain() is only computed for the handful of results actually
        # returned, not every leaf visited during the DFS - it's cheap
        # per-call but there's no reason to pay it thousands of times
        # over for candidates that never make top-K.
        for result in results:
            normalized = self.evaluator.normalize(result.cost_breakdown, features)
            result.contributions = self.evaluator.explain(result.cost_breakdown, normalized, self.strategy)
        return results

    def _build_teams(
        self, rosters: list[list[Player]], preferences: dict[int, RolePreference]
    ) -> list[Team]:
        teams = []
        for index, roster in enumerate(rosters):
            slots = self.position_assigner.assign(roster, preferences)
            teams.append(Team(index=index, players=list(roster), slots=slots))
        return teams

    def _build_warm_start_teams(
        self, ordered_players: list[Player], num_teams: int, preferences: dict[int, RolePreference]
    ) -> list[Team]:
        rosters: list[list[Player]] = [[] for _ in range(num_teams)]
        for tier_index in range(TEAM_SIZE):
            tier_group = ordered_players[tier_index * num_teams : (tier_index + 1) * num_teams]
            team_order = range(num_teams) if tier_index % 2 == 0 else range(num_teams - 1, -1, -1)
            for team_index, player in zip(team_order, tier_group):
                rosters[team_index].append(player)
        return self._build_teams(rosters, preferences)

    def _dfs(
        self,
        players: list[Player],
        player_index: int,
        rosters: list[list[Player]],
        num_teams: int,
        preferences: dict[int, RolePreference],
        on_leaf,
        deadline: float,
    ) -> None:
        if self._nodes_expanded >= self.max_nodes or time.monotonic() > deadline:
            return

        if player_index == len(players):
            self._nodes_expanded += 1
            on_leaf(self._build_teams(rosters, preferences))
            return

        player = players[player_index]
        opened_count = sum(1 for roster in rosters if roster)
        candidate_team_indices = [i for i in range(opened_count) if len(rosters[i]) < TEAM_SIZE]
        if opened_count < num_teams:
            candidate_team_indices.append(opened_count)

        for team_index in candidate_team_indices:
            if self._nodes_expanded >= self.max_nodes or time.monotonic() > deadline:
                break
            rosters[team_index].append(player)
            self._dfs(players, player_index + 1, rosters, num_teams, preferences, on_leaf, deadline)
            rosters[team_index].pop()
