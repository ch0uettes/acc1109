from __future__ import annotations

from abc import ABC, abstractmethod
from collections import Counter
from typing import Optional

import requests

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
        consecutive_empty_batches = 0

        # Bounds how far back the search probes (start offset), not how
        # many entries end up in `collected` - tolerating empty batches
        # below means the loop could otherwise run indefinitely if empty
        # and non-empty batches kept alternating without ever hitting 2
        # consecutive empties.
        while start < self.max_matches:
            try:
                batch = self.riot_client.get_match_history(puuid, count=self.window_step, start=start)
            except requests.exceptions.RequestException:
                # A single failed request (e.g. a 429 that exhausted its
                # retries, or a transient 5xx) late in a multi-batch scan
                # used to discard every batch already collected, turning
                # one flaky request into a total loss of an otherwise-good
                # recommendation. Report on whatever was gathered so far
                # instead of losing it - PlayerService.infer_position
                # already treats a *first-batch* failure as "no
                # recommendation" via its own except clause, so this only
                # changes behavior once there's real partial progress.
                break
            start += self.window_step
            if not batch:
                # get_match_history() can legitimately return [] for a
                # non-empty id batch if every participant lookup in that
                # window missed (see its own docstring) - that's not the
                # same as "no more games exist". Only treat two consecutive
                # empty batches as genuine end-of-history, so one
                # data-inconsistency window doesn't cut the widening
                # search short while later, perfectly fetchable games
                # still exist.
                consecutive_empty_batches += 1
                if consecutive_empty_batches >= 2:
                    break
                continue
            consecutive_empty_batches = 0
            collected.extend(batch)

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
