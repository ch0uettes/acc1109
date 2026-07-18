from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Optional

from app.balance.config import DEFAULT_NORMALIZATION_CONFIG, NormalizationConfig
from app.balance.constraint_engine.executor import ConstraintExecutor
from app.balance.constraint_engine.registry import DEFAULT_CONSTRAINT_REGISTRY, ConstraintRegistry
from app.balance.constraint_engine.result import ConstraintStatus
from app.balance.constraints import HardConstraintLayer
from app.balance.features import DEFAULT_FEATURE_REGISTRY, BalanceEvaluator, FeatureRegistry
from app.balance.result import BalanceResult
from app.balance.search_policy import SEARCH_POLICY_REGISTRY, SearchPolicy, StableSearchPolicy
from app.balance.strategy import DEFAULT_STRATEGY, IBalanceStrategy
from app.models.player import Player
from app.models.team import Team
from app.position.assigner import BipartiteMatchingPositionAssigner, PositionAssigner
from app.position.schemas import RolePreference
from app.utils.enums import Position
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
        self,
        players: list[Player],
        preferences: dict[int, RolePreference],
        k: int = 3,
        override_player_ids: frozenset = frozenset(),
    ) -> list[BalanceResult]:
        """Default fallback for engines that don't natively explore
        multiple distinct candidates: just wraps search() as a
        single-item list. `override_player_ids` (player ids whose
        RolePreference came from an explicit this-match override, not
        their stored profile - see ConstraintContext.override_player_ids)
        is accepted for interface parity but ignored here since search()
        alone can't enforce it; BacktrackingSearchEngine overrides this with a
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

    - Players are processed one at a time, ordered by the active
      SearchPolicy (default: descending final_rating - tightens the
      search early, gives deterministic output; see
      app/balance/search_policy.py for how a Strategy influences which
      candidates get explored, not just how they're scored).
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
        search_policy: Optional[SearchPolicy] = None,
        feature_registry: Optional[FeatureRegistry] = None,
        hard_constraints: Optional[HardConstraintLayer] = None,
        normalization_config: Optional[NormalizationConfig] = None,
        constraint_registry: Optional[ConstraintRegistry] = None,
        constraint_priorities: Optional[dict[str, int]] = None,
        max_nodes: int = 20_000,
        time_budget_seconds: float = 5.0,
        max_cost_ratio: float = 1.25,
    ) -> None:
        """Normal usage: pick `strategy` (Competitive/Comfort/Stable,
        default Stable Mode) and nothing else - the Features to run come
        from `feature_registry.get_active_features(strategy, normalization_config)`
        fresh on every search, so this class never hardcodes which
        Features exist or how many. `search_policy` defaults to whichever
        concrete SearchPolicy is registered under `strategy.name` (falling
        back to StableSearchPolicy), so picking a Strategy also picks a
        matching candidate-exploration order without extra wiring - see
        app/balance/search_policy.py. `normalization_config` is typically a
        Server's saved override (see app/models/server.py); defaults to
        the code-level DEFAULT_NORMALIZATION_CONFIG when not given.
        `max_cost_ratio` bounds how much worse a 2nd/3rd-place combo is
        allowed to be relative to the 1st-place cost before search_top_k()
        drops it instead of showing a misleadingly bad "alternative" (see
        _filter_by_quality). `evaluator`/`feature_registry`/
        `hard_constraints` are only for tests/advanced callers who want to
        swap a piece independently. `constraint_priorities` is typically a
        Server's saved override (see app/models/server.py) - the Server
        component of ConstraintExecutor's Strategy > Server > plugin-default
        priority resolution; same "typically a Server override" role as
        `normalization_config`/`hard_constraints` above."""
        self.position_assigner = position_assigner or BipartiteMatchingPositionAssigner()
        self.evaluator = evaluator or BalanceEvaluator()
        self.strategy = strategy or DEFAULT_STRATEGY
        self.search_policy = search_policy or SEARCH_POLICY_REGISTRY.get(self.strategy.name, StableSearchPolicy)()
        self.feature_registry = feature_registry or DEFAULT_FEATURE_REGISTRY
        self.hard_constraints = hard_constraints or HardConstraintLayer()
        self.normalization_config = normalization_config or DEFAULT_NORMALIZATION_CONFIG
        self.constraint_registry = constraint_registry or DEFAULT_CONSTRAINT_REGISTRY
        self.constraint_priorities = constraint_priorities or {}
        self.max_nodes = max_nodes
        self.time_budget_seconds = time_budget_seconds
        self.max_cost_ratio = max_cost_ratio

    def search(self, players: list[Player], preferences: dict[int, RolePreference]) -> BalanceResult:
        return self.search_top_k(players, preferences, k=1)[0]

    def search_top_k(
        self,
        players: list[Player],
        preferences: dict[int, RolePreference],
        k: int = 3,
        override_player_ids: frozenset = frozenset(),
    ) -> list[BalanceResult]:
        if len(players) == 0 or len(players) % TEAM_SIZE != 0:
            raise InvalidPlayerCountError(
                f"Player count must be a positive multiple of {TEAM_SIZE}, got {len(players)}"
            )

        search_start = time.monotonic()
        num_teams = len(players) // TEAM_SIZE
        ordered = self.search_policy.order_players(players)
        features = self.feature_registry.get_active_features(self.strategy, self.normalization_config)
        # Every hard-enforced this-match override gets pinned directly in
        # PositionAssigner (see BipartiteMatchingPositionAssigner.assign),
        # not just checked after the fact - otherwise the optimizer is
        # free to bump the forced player to a different lane whenever
        # someone else on the same roster also wants their position, and
        # almost every roster containing them would fail FixedRoleConstraint
        # at leaf time for reasons the search has no way to steer around.
        forced_positions: dict[int, Position] = {
            player_id: preferences[player_id].main
            for player_id in override_player_ids
            if player_id in preferences
        }
        top = _TopKResults(k)
        self._nodes_expanded = 0
        # Fresh per call (mirrors _TopKResults(k)) - resolves each tier's
        # active plugin list ONCE here, not per DFS node, and its
        # statistics only ever describe this one search.
        self.constraint_executor = ConstraintExecutor(
            registry=self.constraint_registry, strategy=self.strategy, search_policy=self.search_policy,
            constraint_priorities=self.constraint_priorities,
        )

        def evaluate_and_offer(teams: list[Team]) -> BalanceResult:
            raw = self.evaluator.evaluate_raw(teams, features)
            normalized = self.evaluator.normalize(raw, features)
            cost = self.evaluator.combine(normalized, self.strategy)
            result = BalanceResult(teams=teams, cost=cost, cost_breakdown=raw, iterations=self._nodes_expanded)
            leaf_results = self.constraint_executor.evaluate_leaf(
                teams, players, preferences, override_player_ids
            )
            leaf_ok = not any(r.status == ConstraintStatus.FAIL for r in leaf_results)
            if leaf_ok and self.hard_constraints.is_feasible(teams, raw):
                top.offer(result)
            return result

        custom_warm_start = self.search_policy.warm_start(ordered, num_teams)
        warm_start_teams = (
            self._build_teams(custom_warm_start, preferences, forced_positions)
            if custom_warm_start is not None
            else self._build_warm_start_teams(ordered, num_teams, preferences, forced_positions)
        )
        warm_start_result = evaluate_and_offer(warm_start_teams)

        deadline = time.monotonic() + self.time_budget_seconds
        rosters: list[list[Player]] = [[] for _ in range(num_teams)]
        self._dfs(ordered, 0, rosters, num_teams, preferences, evaluate_and_offer, deadline, forced_positions)

        results = self.search_policy.order_team_candidates(top.results())
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

        # Real per-candidate Constraint Engine results, re-derived for the
        # handful of results actually returned (same "not thousands of
        # times over" reasoning as explain() above) - includes whatever
        # search_top_k() actually returned, warm-start fallback included,
        # so a Hard-violating fallback result is visible rather than
        # silently treated as compliant (see BacktrackingSearchEngine's
        # class docstring on the warm-start guarantee).
        self.last_constraint_results = [
            self.constraint_executor.evaluate_leaf(result.teams, players, preferences, override_player_ids)
            for result in results
        ]

        # Post-call read-only stats for callers building an ExecutionContext
        # (see app/balance/execution_context.py) - set every call, not
        # accumulated, so they always describe only the most recent search.
        self.last_nodes_expanded = self._nodes_expanded
        self.last_elapsed_seconds = time.monotonic() - search_start
        self.last_node_budget_hit = self._nodes_expanded >= self.max_nodes
        self.last_time_budget_hit = time.monotonic() > deadline
        self.last_constraint_statistics = self.constraint_executor.statistics()
        return results

    def _build_teams(
        self,
        rosters: list[list[Player]],
        preferences: dict[int, RolePreference],
        forced_positions: dict[int, Position] | None = None,
    ) -> list[Team]:
        forced_positions = forced_positions or {}
        teams = []
        for index, roster in enumerate(rosters):
            roster_forced = {p.id: forced_positions[p.id] for p in roster if p.id in forced_positions}
            slots = self.position_assigner.assign(roster, preferences, forced_positions=roster_forced)
            teams.append(Team(index=index, players=list(roster), slots=slots))
        return teams

    def _build_warm_start_teams(
        self,
        ordered_players: list[Player],
        num_teams: int,
        preferences: dict[int, RolePreference],
        forced_positions: dict[int, Position] | None = None,
    ) -> list[Team]:
        rosters: list[list[Player]] = [[] for _ in range(num_teams)]
        for tier_index in range(TEAM_SIZE):
            tier_group = ordered_players[tier_index * num_teams : (tier_index + 1) * num_teams]
            team_order = range(num_teams) if tier_index % 2 == 0 else range(num_teams - 1, -1, -1)
            for team_index, player in zip(team_order, tier_group):
                rosters[team_index].append(player)
        return self._build_teams(rosters, preferences, forced_positions)

    def _dfs(
        self,
        players: list[Player],
        player_index: int,
        rosters: list[list[Player]],
        num_teams: int,
        preferences: dict[int, RolePreference],
        on_leaf,
        deadline: float,
        forced_positions: dict[int, Position] | None = None,
    ) -> None:
        if self._nodes_expanded >= self.max_nodes or time.monotonic() > deadline:
            return

        if player_index == len(players):
            self._nodes_expanded += 1
            on_leaf(self._build_teams(rosters, preferences, forced_positions))
            return

        player = players[player_index]
        opened_count = sum(1 for roster in rosters if roster)
        candidate_team_indices = [i for i in range(opened_count) if len(rosters[i]) < TEAM_SIZE]
        if opened_count < num_teams:
            candidate_team_indices.append(opened_count)

        # Partial-Hard pruning (Constraint Engine) - drops any branch a
        # monotonic PartialHardConstraint rejects before recursing into it
        # at all. No-op with the default registry (zero concrete
        # PartialHardConstraint plugins ship this pass - see
        # app/balance/constraint_engine), so this can't change behavior
        # for any Strategy shipped today.
        candidate_team_indices = [
            team_index
            for team_index in candidate_team_indices
            if not any(
                result.prune
                for result in self.constraint_executor.evaluate_partial(
                    rosters, team_index, player, players, preferences
                )
            )
        ]

        # Search Guidance (Constraint Engine) - reorders survivors by
        # ascending combined Soft+Preference penalty/heuristic (lowest
        # explored first). No-op with the default registry (zero concrete
        # Soft/Preference plugins ship this pass), and `sorted()` is
        # stable, so an empty registry reproduces today's exact order.
        guidance = self.constraint_executor.compute_search_guidance(
            rosters, candidate_team_indices, player, players, preferences
        )
        if guidance:
            candidate_team_indices = sorted(
                candidate_team_indices, key=lambda i: guidance[i].total_score
            )

        candidate_team_indices = self.search_policy.branch_priority(player, candidate_team_indices, rosters)

        for team_index in candidate_team_indices:
            if self._nodes_expanded >= self.max_nodes or time.monotonic() > deadline:
                break
            rosters[team_index].append(player)
            self._dfs(players, player_index + 1, rosters, num_teams, preferences, on_leaf, deadline, forced_positions)
            rosters[team_index].pop()
