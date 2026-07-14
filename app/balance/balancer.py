from __future__ import annotations

from app.balance.config import NormalizationConfig
from app.balance.constraints import HardConstraintLayer
from app.balance.result import BalanceResult
from app.balance.search_engine import BacktrackingSearchEngine, TeamSearchEngine
from app.balance.strategy import IBalanceStrategy
from app.position.preference_manager import RolePreferenceManager
from app.position.signup import PlayerSignup


class TeamBalancer:
    """Entry point services/UI call. Thin orchestrator only: resolves each
    signup's RolePreference (this-match override -> Player Profile) via
    RolePreferenceManager, then delegates the actual team-membership +
    position-assignment search to TeamSearchEngine. No evaluation or
    search logic lives here - see BalanceEvaluator/TeamSearchEngine for
    that, so a Discord Bot/Web/Mobile layer can call this same Core
    Engine without touching Streamlit."""

    def __init__(
        self,
        search_engine: TeamSearchEngine | None = None,
        preference_manager: RolePreferenceManager | None = None,
        strategy: IBalanceStrategy | None = None,
        normalization_config: NormalizationConfig | None = None,
        hard_constraints: HardConstraintLayer | None = None,
    ) -> None:
        """`strategy`/`normalization_config`/`hard_constraints` only apply
        when `search_engine` isn't supplied directly - they're forwarded
        straight to BacktrackingSearchEngine's own default construction,
        so TeamBalancer itself never touches Feature or evaluator
        internals. `normalization_config`/`hard_constraints` are
        typically a Server's saved override (see app/models/server.py)."""
        self.search_engine = search_engine or BacktrackingSearchEngine(
            strategy=strategy, normalization_config=normalization_config, hard_constraints=hard_constraints
        )
        self.preference_manager = preference_manager or RolePreferenceManager()

    def generate_teams(self, signups: list[PlayerSignup]) -> BalanceResult:
        players, preferences = self._resolve(signups)
        return self.search_engine.search(players, preferences)

    def generate_top_teams(self, signups: list[PlayerSignup], k: int = 3) -> list[BalanceResult]:
        """Same pipeline as generate_teams(), but returns the best `k`
        distinct team-membership combinations instead of just one - the
        engine explores them in a single pass, no extra search cost."""
        players, preferences = self._resolve(signups)
        return self.search_engine.search_top_k(players, preferences, k=k)

    def _resolve(self, signups: list[PlayerSignup]):
        players = [signup.player for signup in signups]
        preferences = {
            signup.player.id: self.preference_manager.resolve(signup.player, signup.match_override)
            for signup in signups
        }
        return players, preferences
