from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from app.balance.result import BalanceResult
from app.models.player import Player
from app.utils.enums import Position


class SearchPolicy(ABC):
    """Strategy → SearchPolicy → Candidate Generator → BalanceEvaluator.
    Where IBalanceStrategy only decides *how a candidate is scored*
    (feature weights), SearchPolicy decides *which candidates the search
    explores in the first place* - without this, a budgeted DFS with a
    single fixed traversal order finds the same candidates regardless of
    Strategy, and only final-leaf scoring differs (confirmed bug: all 3
    Strategies converged on identical team splits before this class
    existed).

    Four extension points, only the first exercised by any concrete
    Strategy shipped in v1.0 - the other three exist so a future
    Tournament/Draft/ARAM policy can hook into the search engine without
    any change to BacktrackingSearchEngine itself. Every default
    reproduces today's engine behavior exactly (identity/no-op), which is
    what keeps existing search-engine tests green under the Stable
    default."""

    name: str

    @abstractmethod
    def order_players(self, players: list[Player]) -> list[Player]:
        """Controls both warm-start seeding order and DFS traversal
        order (BacktrackingSearchEngine reads this single ordered list
        for both) - the one hook every v1.0 policy actually overrides."""
        ...

    def warm_start(self, ordered_players: list[Player], num_teams: int) -> Optional[list[list[Player]]]:
        """None (default) = let the engine build its own snake-draft warm
        start from `ordered_players`. A future Tournament/Draft policy can
        return a fully custom seed partition (list of `num_teams` rosters)
        instead."""
        return None

    def branch_priority(
        self, player: Player, candidate_team_indices: list[int], rosters: list[list[Player]]
    ) -> list[int]:
        """Identity (default) = today's fixed ascending-team-index branch
        order. A future policy can reorder which not-yet-full team the
        DFS tries first for a given player."""
        return candidate_team_indices

    def order_team_candidates(self, results: list[BalanceResult]) -> list[BalanceResult]:
        """Identity (default) - results already arrive cost-sorted from
        _TopKResults. A future policy (e.g. breaking cost-ties by
        role-fit) can override this final ordering step."""
        return results


class StableSearchPolicy(SearchPolicy):
    """Default - reproduces the search engine's original behavior
    exactly: process highest-rated players first."""

    name = "stable"

    def order_players(self, players: list[Player]) -> list[Player]:
        return sorted(players, key=lambda p: p.final_rating, reverse=True)


class CompetitiveSearchPolicy(SearchPolicy):
    """대회/스크림형 - 라인전 공정성이 최우선이므로, 같은 라인끼리 먼저
    묶어 그 안에서 Rating 순으로 정렬한다. 이렇게 하면 예산 내에서 탐색이
    라인별로 균형 잡힌 분배를 더 일찍, 더 자주 발견하게 된다 (라인 정보를
    무시하고 전체 Rating 순으로만 정렬하는 Stable과의 핵심 차이)."""

    name = "competitive"

    def order_players(self, players: list[Player]) -> list[Player]:
        role_order = list(Position)
        return sorted(
            players,
            key=lambda p: (role_order.index(p.main_role), -p.final_rating),
        )


class ComfortSearchPolicy(SearchPolicy):
    """친구/캐주얼 내전 - 원하는 포지션을 최대한 존중하는 것이 최우선이므로,
    Riot 추천 포지션 확신도가 높은 플레이어를 먼저 배치해 그 선호가 예산
    소진 전에 반영될 가능성을 높인다. 확신도 데이터가 없는 플레이어(수동
    등록 등)는 확신도 0으로 취급해 뒤로 밀린다."""

    name = "comfort"

    def order_players(self, players: list[Player]) -> list[Player]:
        return sorted(
            players,
            key=lambda p: (-(p.recommended_main_confidence or 0.0), -p.final_rating),
        )


SEARCH_POLICY_REGISTRY: dict[str, type[SearchPolicy]] = {
    "competitive": CompetitiveSearchPolicy,
    "comfort": ComfortSearchPolicy,
    "stable": StableSearchPolicy,
}

DEFAULT_SEARCH_POLICY: SearchPolicy = StableSearchPolicy()
