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
    """대회/스크림/경쟁형 내전 - 라인전 공정성을 최우선으로 평가."""

    name = "competitive"

    def feature_config(self) -> dict[str, FeatureConfig]:
        return {
            "lane_balance": FeatureConfig(enabled=True, weight=0.35),
            "average_rating": FeatureConfig(enabled=True, weight=0.25),
            "internal_rating": FeatureConfig(enabled=True, weight=0.20),
            "tier_distribution": FeatureConfig(enabled=True, weight=0.10),
            "team_variance": FeatureConfig(enabled=True, weight=0.05),
            "role_penalty": FeatureConfig(enabled=True, weight=0.03),
        }


class ComfortStrategy(IBalanceStrategy):
    """친구/캐주얼 내전 - 참가자가 원하는 Main/Sub 포지션을 최대한
    존중하는 것을 최우선으로 평가. 약간의 라인 Rating 격차는 감수한다."""

    name = "comfort"

    def feature_config(self) -> dict[str, FeatureConfig]:
        return {
            "role_penalty": FeatureConfig(enabled=True, weight=0.35),
            "average_rating": FeatureConfig(enabled=True, weight=0.20),
            "internal_rating": FeatureConfig(enabled=True, weight=0.15),
            "lane_balance": FeatureConfig(enabled=True, weight=0.10),
            "team_variance": FeatureConfig(enabled=True, weight=0.10),
            "tier_distribution": FeatureConfig(enabled=True, weight=0.05),
        }


class StableStrategy(IBalanceStrategy):
    """기본(Default) Strategy - 대부분의 일반 내전에 적합. 팀 간 평균
    Rating 격차가 가장 근본적인 공정성 기준이므로 average_rating이
    항상 최고 가중치를 갖는다. team_variance/tier_distribution("체감
    밸런스" - 한 팀에 캐리 1명 + 약자 4명처럼 팀 내부가 극단적으로
    쏠리지 않는 것)은 그다음으로 무겁게 평가하되, average_rating보다
    낮게 둔다 - 그렇지 않으면 비슷한 티어끼리 팀 내부적으로만 뭉쳐서
    팀 간 평균 격차를 오히려 키우는 조합이 구조적으로 유리해질 수
    있다 (team_variance는 "팀 간 평균이 비슷할 때 그중 더 나은 조합을
    고르는" 보조 기준이어야 한다)."""

    name = "stable"

    def feature_config(self) -> dict[str, FeatureConfig]:
        return {
            "average_rating": FeatureConfig(enabled=True, weight=0.25),
            "team_variance": FeatureConfig(enabled=True, weight=0.20),
            "tier_distribution": FeatureConfig(enabled=True, weight=0.20),
            "lane_balance": FeatureConfig(enabled=True, weight=0.15),
            "internal_rating": FeatureConfig(enabled=True, weight=0.15),
            "role_penalty": FeatureConfig(enabled=True, weight=0.03),
        }


# New Strategy = new class + one registry entry. BalanceEvaluator and
# every existing Feature/Strategy stay untouched.
STRATEGY_REGISTRY: dict[str, type[IBalanceStrategy]] = {
    "competitive": CompetitiveStrategy,
    "comfort": ComfortStrategy,
    "stable": StableStrategy,
}

DEFAULT_STRATEGY: IBalanceStrategy = StableStrategy()
