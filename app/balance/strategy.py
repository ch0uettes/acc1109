from __future__ import annotations

from abc import ABC, abstractmethod

from app.balance.config import FeatureConfig


class IBalanceStrategy(ABC):
    """A Strategy answers only "which Features matter, and how much" -
    never "how does a Feature compute its score" (IBalanceFeature's job)
    and never "how do I search for a team split" (TeamSearchEngine's
    job). Strategies and Features are intentionally unaware of each
    other: a Strategy returns a plain dict[str, FeatureConfig] keyed by
    Feature *name* (a string), never imports or references a Feature
    class directly. A new Strategy is just a new feature_config() - it
    never touches an existing Feature, and a new Feature never touches an
    existing Strategy."""

    name: str

    @abstractmethod
    def feature_config(self) -> dict[str, FeatureConfig]:
        ...

    def is_enabled(self, feature_name: str) -> bool:
        config = self.feature_config().get(feature_name)
        return config is not None and config.enabled

    def get_weight(self, feature_name: str) -> float:
        config = self.feature_config().get(feature_name)
        return config.weight if config is not None else 0.0

    def constraint_priority_overrides(self) -> dict[str, int]:
        """Optional per-Strategy override of a Constraint plugin's
        default_priority (see app/balance/constraint_engine) - e.g. a
        future CompetitiveStrategy might return {"lane_gap": 90} to check
        that constraint earliest under Competitive mode specifically.
        Non-abstract with an empty default so none of today's concrete
        Strategies need to implement anything; ConstraintExecutor's
        priority resolution checks this before falling back to a
        Server's saved override, then finally the plugin's own
        default_priority."""
        return {}


class CompetitiveStrategy(IBalanceStrategy):
    """대회/스크림/경쟁형 내전 - 라인전 공정성을 최우선으로 평가.
    outlier_penalty(가장 튀는 팀 하나의 절대 편차)를 추가해 lane_balance
    만으로 못 잡는 "한 팀 전체가 유독 강한" 경우도 함께 억제한다."""

    name = "competitive"

    def feature_config(self) -> dict[str, FeatureConfig]:
        return {
            "lane_balance": FeatureConfig(enabled=True, weight=0.30),
            "mean_balance": FeatureConfig(enabled=True, weight=0.20),
            "outlier_penalty": FeatureConfig(enabled=True, weight=0.20),
            "internal_rating": FeatureConfig(enabled=True, weight=0.15),
            "tier_distribution": FeatureConfig(enabled=True, weight=0.08),
            "team_variance": FeatureConfig(enabled=True, weight=0.04),
            "role_penalty": FeatureConfig(enabled=True, weight=0.03),
        }


class ComfortStrategy(IBalanceStrategy):
    """친구/캐주얼 내전 - 참가자가 원하는 Main/Sub 포지션을 최대한
    존중하는 것을 최우선으로 평가. 약간의 라인 Rating 격차는 감수한다."""

    name = "comfort"

    def feature_config(self) -> dict[str, FeatureConfig]:
        return {
            "role_penalty": FeatureConfig(enabled=True, weight=0.32),
            "mean_balance": FeatureConfig(enabled=True, weight=0.18),
            "outlier_penalty": FeatureConfig(enabled=True, weight=0.15),
            "internal_rating": FeatureConfig(enabled=True, weight=0.13),
            "lane_balance": FeatureConfig(enabled=True, weight=0.10),
            "team_variance": FeatureConfig(enabled=True, weight=0.08),
            "tier_distribution": FeatureConfig(enabled=True, weight=0.04),
        }


class StableStrategy(IBalanceStrategy):
    """기본(Default) Strategy - 대부분의 일반 내전에 적합. 세 Feature가
    서로 다른 책임으로 명확히 분리되어 있다:

    - mean_balance: 모든 팀 평균이 전체 평균을 중심으로 얼마나 고르게
      분포하는가 (전체적인 평균 균형).
    - outlier_penalty: 가장 튀는 팀 "하나"가 전체 평균에서 얼마나
      벗어났는가 (극단적인 팀 생성 방지) - mean_balance와 달리 다른
      팀들이 아무리 고르게 뭉쳐 있어도 이 팀 하나가 튀면 강하게
      페널티를 받는다.
    - team_variance: 각 팀 "내부" 티어가 얼마나 들쭉날쭉한가 (팀 내부
      안정성) - 팀 간 평균 격차는 전혀 담당하지 않는다.

    mean_balance + outlier_penalty(둘 다 "팀 간" 격차를 보는 항목)의
    합이 team_variance보다 항상 훨씬 커야 한다 - 그렇지 않으면 비슷한
    티어끼리 팀 내부적으로만 뭉쳐서 팀 간 평균 격차를 오히려 키우는
    조합이 구조적으로 유리해질 수 있다."""

    name = "stable"

    def feature_config(self) -> dict[str, FeatureConfig]:
        return {
            "mean_balance": FeatureConfig(enabled=True, weight=0.28),
            "outlier_penalty": FeatureConfig(enabled=True, weight=0.27),
            "lane_balance": FeatureConfig(enabled=True, weight=0.18),
            "team_variance": FeatureConfig(enabled=True, weight=0.12),
            "tier_distribution": FeatureConfig(enabled=True, weight=0.08),
            "internal_rating": FeatureConfig(enabled=True, weight=0.05),
            "role_penalty": FeatureConfig(enabled=True, weight=0.02),
        }


# New Strategy = new class + one registry entry. BalanceEvaluator and
# every existing Feature/Strategy stay untouched.
STRATEGY_REGISTRY: dict[str, type[IBalanceStrategy]] = {
    "competitive": CompetitiveStrategy,
    "comfort": ComfortStrategy,
    "stable": StableStrategy,
}

DEFAULT_STRATEGY: IBalanceStrategy = StableStrategy()
