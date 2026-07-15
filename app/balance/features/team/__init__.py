from __future__ import annotations

from app.balance.features.base import IBalanceFeature
from app.balance.features.team.penalty import PenaltyFeature

# Team category: generic team-composition hard constraints that don't
# belong to Rating/Lane/Distribution/Learning (e.g. keep/split specific
# players). Currently only PenaltyFeature, which is unimplemented and
# disabled by default - see its own docstring.
TEAM_FEATURES: dict[str, type[IBalanceFeature]] = {
    "penalty": PenaltyFeature,
}

__all__ = [
    "PenaltyFeature",
    "TEAM_FEATURES",
]
