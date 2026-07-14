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


class CompetitiveStrategy(IBalanceStrategy):
    """대회/스크림/경쟁형 내전 - 라인전 공정성을 최우선으로 평가.
    inter_team_balance(팀 간 평균 분산)를 추가해 lane_balance만으로
    못 잡는 "한 팀 전체가 유독 강한" 경우도 함께 억제한다."""

    name = "competitive"

    def feature_config(self) -> dict[str, FeatureConfig]:
        return {
            "lane_balance": FeatureConfig(enabled=True, weight=0.30),
            "average_rating": FeatureConfig(enabled=True, weight=0.20),
            "inter_team_balance": FeatureConfig(enabled=True, weight=0.20),
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
            "average_rating": FeatureConfig(enabled=True, weight=0.18),
            "inter_team_balance": FeatureConfig(enabled=True, weight=0.15),
            "internal_rating": FeatureConfig(enabled=True, weight=0.13),
            "lane_balance": FeatureConfig(enabled=True, weight=0.10),
            "team_variance": FeatureConfig(enabled=True, weight=0.08),
            "tier_distribution": FeatureConfig(enabled=True, weight=0.04),
        }


class StableStrategy(IBalanceStrategy):
    """기본(Default) Strategy - 대부분의 일반 내전에 적합. 팀 간 평균
    Rating 격차가 가장 근본적인 공정성 기준이므로 inter_team_balance/
    average_rating이 항상 가장 높은 가중치를 갖는다 (둘 다 "팀 간"
    격차를 다른 통계량으로 보는 항목 - inter_team_balance는 분산이라
    팀 하나가 유독 튀는 경우를 강하게 잡아내고, average_rating은
    표준편차라 전체적으로 고르게 퍼진 정도를 선형적으로 잡아낸다).
    team_variance("한 팀 내부가 캐리 1명 + 약자 4명처럼 쏠리지 않는
    것")는 그보다 훨씬 낮게 둔다 - 그렇지 않으면 비슷한 티어끼리 팀
    내부적으로만 뭉쳐서 팀 간 평균 격차를 오히려 키우는 조합이
    구조적으로 유리해질 수 있다 (team_variance는 "팀 간 평균이 비슷할
    때 그중 더 나은 조합을 고르는" 보조 기준이어야 한다)."""

    name = "stable"

    def feature_config(self) -> dict[str, FeatureConfig]:
        return {
            "inter_team_balance": FeatureConfig(enabled=True, weight=0.30),
            "average_rating": FeatureConfig(enabled=True, weight=0.25),
            "lane_balance": FeatureConfig(enabled=True, weight=0.20),
            "team_variance": FeatureConfig(enabled=True, weight=0.10),
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
