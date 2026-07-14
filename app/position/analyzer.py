from __future__ import annotations

from abc import ABC, abstractmethod
from collections import Counter
from typing import Optional

from app.position.schemas import RoleRecommendation
from app.riot.client import RiotAPIClient

# Look at the most recent MIN_MATCHES_FOR_POSITION ranked games. If the top
# position doesn't clear CONFIDENT_POSITION_RATIO of those games (the player
# swaps lines a lot), widen the window by POSITION_WINDOW_STEP more games and
# re-check, up to MAX_MATCHES_FOR_POSITION.
MIN_MATCHES_FOR_POSITION = 20
POSITION_WINDOW_STEP = 20
MAX_MATCHES_FOR_POSITION = 100
CONFIDENT_POSITION_RATIO = 0.6


class PositionAnalyzer(ABC):
    """Analyzes real play history into a Main/Sub role recommendation.
    Deliberately independent of RiotAPIClient's own interface - it's a
    *consumer* of match history, not part of the Riot API binding, so a
    future non-Riot data source (OCR history, manual import) can implement
    this same interface without touching RiotAPIClient at all."""

    @abstractmethod
    def recommend(self, puuid: str) -> Optional[RoleRecommendation]:
        """None if the account has no ranked match history to infer from."""


class RiotHistoryPositionAnalyzer(PositionAnalyzer):
    """Pages through a RiotAPIClient's ranked match history, widening the
    window until one position's share is confident enough or the max
    window is hit, then reports the top-2 most-played positions as
    Main/Sub. This owns the widening-window algorithm that used to live
    inside LiveRiotAPIClient.infer_primary_position - RiotAPIClient itself
    now only exposes raw match history, no position-inference logic."""

    def __init__(
        self,
        riot_client: RiotAPIClient,
        window_step: int = POSITION_WINDOW_STEP,
        max_matches: int = MAX_MATCHES_FOR_POSITION,
        confident_ratio: float = CONFIDENT_POSITION_RATIO,
    ) -> None:
        self.riot_client = riot_client
        self.window_step = window_step
        self.max_matches = max_matches
        self.confident_ratio = confident_ratio

    def recommend(self, puuid: str) -> Optional[RoleRecommendation]:
        collected = []
        start = 0

        while True:
            batch = self.riot_client.get_match_history(puuid, count=self.window_step, start=start)
            if not batch:
                break
            collected.extend(batch)
            start += self.window_step

            counts = Counter(e.position for e in collected)
            _, top_count = counts.most_common(1)[0]
            ratio = top_count / len(collected)
            if ratio >= self.confident_ratio or len(collected) >= self.max_matches:
                break

        if not collected:
            return None

        counts = Counter(e.position for e in collected)
        ranked = counts.most_common(2)
        main_position, main_count = ranked[0]

        sub_position = None
        sub_ratio = None
        if len(ranked) > 1:
            sub_position, sub_count = ranked[1]
            sub_ratio = sub_count / len(collected)

        return RoleRecommendation(
            main=main_position,
            main_ratio=main_count / len(collected),
            sub=sub_position,
            sub_ratio=sub_ratio,
            sample_size=len(collected),
        )
