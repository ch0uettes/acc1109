from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Optional
from urllib.parse import quote

import requests

from app.config import settings
from app.riot.schemas import ChampionMasteryEntry, MatchHistoryEntry, RankInfo, RiotAccount
from app.utils.enums import Division, Position, Tier

SOLO_QUEUE = "RANKED_SOLO_5x5"
RANKED_SOLO_QUEUE_ID = 420  # Match-V5 numeric queue id for ranked solo/duo

# Personal/dev Riot API keys are rate-limited (~20 req/s, 100 req/2min).
# Match-V5 detail lookups are one request per match, so a short delay
# between them keeps a whole-roster position scan from tripping a 429.
MATCH_DETAIL_REQUEST_DELAY_SECONDS = 1.3

_TEAM_POSITION_MAP: dict[str, Position] = {
    "TOP": Position.TOP,
    "JUNGLE": Position.JUNGLE,
    "MIDDLE": Position.MID,
    "BOTTOM": Position.ADC,
    "UTILITY": Position.SUPPORT,
}

# Real Riot API still reports GRANDMASTER/CHALLENGER as separate tiers with
# their own independent LP counters. Our domain model collapses all three
# into one Tier.MASTER bucket with continuous LP (see rating/official.py),
# so climbing above Master has to be re-based onto that single scale. These
# offsets are arbitrary but preserve the real ordering Challenger > GM > Master.
GRANDMASTER_LP_OFFSET = 1000
CHALLENGER_LP_OFFSET = 2000


class RiotAPIClient(ABC):
    """Interface for the Riot API integration. Kept independent of any one
    HTTP implementation so services can depend on this today and swap the
    binding (or mock it in tests) without touching callers."""

    @abstractmethod
    def get_account_by_riot_id(self, game_name: str, tag_line: str) -> RiotAccount:
        ...

    @abstractmethod
    def get_rank(self, puuid: str) -> Optional[RankInfo]:
        """None if the account has no ranked solo queue entry this season."""

    @abstractmethod
    def has_ranked_solo_history(self, puuid: str) -> bool:
        """True if the account has ever played a ranked solo match, even if
        it has no current-season entry. This is what lets Case 2 (played
        before, unranked now) be told apart from Case 3 (never ranked)
        without asking the user - Riot just doesn't expose the actual peak
        tier from past seasons, only whether ranked history exists at all."""

    @abstractmethod
    def get_match_history(self, puuid: str, count: int = 20, start: int = 0) -> list[MatchHistoryEntry]:
        ...

    @abstractmethod
    def get_champion_mastery(self, puuid: str) -> list[ChampionMasteryEntry]:
        ...


class NotImplementedRiotAPIClient(RiotAPIClient):
    """Bound when no RIOT_API_KEY is configured. Fails loudly instead of silently."""

    def get_account_by_riot_id(self, game_name: str, tag_line: str) -> RiotAccount:
        raise NotImplementedError("RIOT_API_KEY is not configured")

    def get_rank(self, puuid: str) -> Optional[RankInfo]:
        raise NotImplementedError("RIOT_API_KEY is not configured")

    def has_ranked_solo_history(self, puuid: str) -> bool:
        raise NotImplementedError("RIOT_API_KEY is not configured")

    def get_match_history(self, puuid: str, count: int = 20, start: int = 0) -> list[MatchHistoryEntry]:
        raise NotImplementedError("RIOT_API_KEY is not configured")

    def get_champion_mastery(self, puuid: str) -> list[ChampionMasteryEntry]:
        raise NotImplementedError("Champion mastery lookup is not implemented yet")


def _convert_riot_rank(riot_tier: str, riot_division: str, riot_lp: int) -> tuple[Tier, Division, int]:
    """Maps a raw League-V4 entry onto our (Tier, Division, lp) scale."""
    if riot_tier == "CHALLENGER":
        return Tier.MASTER, Division.IV, riot_lp + CHALLENGER_LP_OFFSET
    if riot_tier == "GRANDMASTER":
        return Tier.MASTER, Division.IV, riot_lp + GRANDMASTER_LP_OFFSET
    if riot_tier == "MASTER":
        return Tier.MASTER, Division.IV, riot_lp
    return Tier(riot_tier), Division(riot_division), riot_lp


class LiveRiotAPIClient(RiotAPIClient):
    """Real Account-V1 + League-V4 client.

    Account-V1 (Riot ID -> PUUID) lives on the continental routing value
    (americas/asia/europe); League-V4 (rank entries) lives on the platform
    routing value (kr/na1/euw1/...). Both are required and configured
    separately because Riot's routing is split this way.
    """

    # A dev key's ~100 req/2min budget is shared across every call this
    # process makes - MATCH_DETAIL_REQUEST_DELAY_SECONDS alone only paces
    # requests *within* one get_match_history() call, so it still gets
    # exhausted when several players' position inference (each one its own
    # ~20-match history fetch) run back to back, e.g. during bulk
    # registration (see player_page.py's "스크린샷으로 일괄 등록" tab -
    # observed directly in production). Riot's 429 response includes a
    # Retry-After header telling us exactly how long the window needs to
    # drain; honoring it directly (bounded to a few attempts) recovers
    # automatically instead of surfacing as a crash.
    RATE_LIMIT_MAX_RETRIES = 3
    RATE_LIMIT_DEFAULT_WAIT_SECONDS = 2.0

    def __init__(self, api_key: str, platform: str = "kr", region: str = "asia") -> None:
        self.api_key = api_key
        self.platform = platform
        self.region = region

    def _get(self, url: str) -> dict | list:
        for attempt in range(self.RATE_LIMIT_MAX_RETRIES + 1):
            response = requests.get(url, headers={"X-Riot-Token": self.api_key}, timeout=10)
            if response.status_code == 429 and attempt < self.RATE_LIMIT_MAX_RETRIES:
                try:
                    wait_seconds = float(response.headers.get("Retry-After", self.RATE_LIMIT_DEFAULT_WAIT_SECONDS))
                except ValueError:
                    wait_seconds = self.RATE_LIMIT_DEFAULT_WAIT_SECONDS
                time.sleep(wait_seconds)
                continue
            response.raise_for_status()
            return response.json()
        raise AssertionError("unreachable")  # loop always returns or raises on its final iteration

    def get_account_by_riot_id(self, game_name: str, tag_line: str) -> RiotAccount:
        # game_name/tag_line are raw operator input dropped straight into a
        # URL path - a Riot ID with a space in the name (extremely common:
        # "Hide on bush#KR1") or a Korean custom tag (see the Hangul tag
        # support added to the OCR roster parser) is neither valid ASCII
        # nor a valid raw URL path segment unescaped. Percent-encoding here
        # is what makes those lookups actually reach the right account
        # instead of silently 404ing as "player not found".
        url = (
            f"https://{self.region}.api.riotgames.com"
            f"/riot/account/v1/accounts/by-riot-id/{quote(game_name.strip(), safe='')}/{quote(tag_line.strip(), safe='')}"
        )
        data = self._get(url)
        return RiotAccount(puuid=data["puuid"], game_name=data["gameName"], tag_line=data["tagLine"])

    def get_rank(self, puuid: str) -> Optional[RankInfo]:
        url = f"https://{self.platform}.api.riotgames.com/lol/league/v4/entries/by-puuid/{puuid}"
        entries = self._get(url)
        solo_entry = next((e for e in entries if e["queueType"] == SOLO_QUEUE), None)
        if solo_entry is None:
            return None

        tier, division, lp = _convert_riot_rank(solo_entry["tier"], solo_entry.get("rank", "IV"), solo_entry["leaguePoints"])
        return RankInfo(
            tier=tier,
            division=division,
            lp=lp,
            wins=solo_entry["wins"],
            losses=solo_entry["losses"],
        )

    def has_ranked_solo_history(self, puuid: str) -> bool:
        url = (
            f"https://{self.region}.api.riotgames.com"
            f"/lol/match/v5/matches/by-puuid/{puuid}/ids?queue={RANKED_SOLO_QUEUE_ID}&count=1"
        )
        match_ids = self._get(url)
        return len(match_ids) > 0

    def get_match_history(self, puuid: str, count: int = 20, start: int = 0) -> list[MatchHistoryEntry]:
        ids_url = (
            f"https://{self.region}.api.riotgames.com"
            f"/lol/match/v5/matches/by-puuid/{puuid}/ids"
            f"?queue={RANKED_SOLO_QUEUE_ID}&start={start}&count={count}"
        )
        match_ids = self._get(ids_url)

        entries: list[MatchHistoryEntry] = []
        for match_id in match_ids:
            detail_url = f"https://{self.region}.api.riotgames.com/lol/match/v5/matches/{match_id}"
            detail = self._get(detail_url)
            participant = next((p for p in detail["info"]["participants"] if p["puuid"] == puuid), None)
            if participant is None:
                # match_id came from this exact puuid's own /ids lookup, so
                # this "shouldn't" happen - but it does in practice (a
                # renamed/merged account whose historical match data still
                # references an old puuid, a data inconsistency right after
                # the match completes, ...), observed directly in
                # production as an uncaught StopIteration crashing the
                # whole position-inference pass. One unreadable match must
                # not take out every other match in the batch.
                time.sleep(MATCH_DETAIL_REQUEST_DELAY_SECONDS)
                continue
            position = _TEAM_POSITION_MAP.get(participant.get("teamPosition", ""))
            if position is None:
                # Match-V5 can legitimately report an empty/unrecognized
                # teamPosition (an early remake, or an occasional backend
                # role-inference miss) even for an otherwise-valid ranked
                # game. Defaulting that to MID used to silently count a
                # game the player may never have actually played mid
                # towards their Main/Sub ratio - skipping it (like the
                # missing-participant case above) keeps the sample honest
                # instead of quietly polluting it.
                time.sleep(MATCH_DETAIL_REQUEST_DELAY_SECONDS)
                continue
            entries.append(
                MatchHistoryEntry(
                    match_id=match_id,
                    champion=participant["championName"],
                    position=position,
                    win=participant["win"],
                )
            )
            time.sleep(MATCH_DETAIL_REQUEST_DELAY_SECONDS)
        return entries

    def get_champion_mastery(self, puuid: str) -> list[ChampionMasteryEntry]:
        raise NotImplementedError("Champion mastery lookup is not implemented yet")


def build_riot_client() -> RiotAPIClient:
    """DI entry point: returns a working client if RIOT_API_KEY is set,
    otherwise a client that fails loudly on first use."""
    if not settings.riot_api_key:
        return NotImplementedRiotAPIClient()
    return LiveRiotAPIClient(
        api_key=settings.riot_api_key,
        platform=settings.riot_platform,
        region=settings.riot_region,
    )
