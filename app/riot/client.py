from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Optional
from urllib.parse import quote

import requests

from app.config import settings
from app.riot.schemas import ChampionMasteryEntry, MatchHistoryEntry, RankInfo, RiotAccount
from app.utils.enums import Division, Position, Tier

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

SOLO_QUEUE = "RANKED_SOLO_5x5"
RANKED_SOLO_QUEUE_ID = 420  # Match-V5 numeric queue id for ranked solo/duo

# Personal/dev Riot API keys are rate-limited (~20 req/s, 100 req/2min).
# Match-V5 detail lookups are one request per match, so a short delay
# between them keeps a whole-roster position scan from tripping a 429.
# Short pause between match-detail requests. It used to be 1.3s to stay
# under a dev key's 100 req/2min on its own, but 20 matches then took 26s+
# and every position inference blew Vercel's 30s function limit (observed
# in production as "Failed to fetch"). Bursts are now absorbed by the 429
# Retry-After handling in _get instead, bounded by the caller's deadline.
MATCH_DETAIL_REQUEST_DELAY_SECONDS = 0.05


class RiotTimeBudgetExceeded(requests.exceptions.Timeout):
    """The caller's time budget (LiveRiotAPIClient.deadline) ran out. A
    requests Timeout, so callers that already treat any RequestException
    as "stop and use what was gathered" handle it without changes."""

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


RIOT_KEY_MISSING_MESSAGE = "Riot API 키가 설정되지 않았습니다 - 서버 관리 → Riot API 키에서 저장해주세요."


class NotImplementedRiotAPIClient(RiotAPIClient):
    """Bound when no RIOT_API_KEY is configured. Fails loudly instead of silently."""

    def get_account_by_riot_id(self, game_name: str, tag_line: str) -> RiotAccount:
        raise NotImplementedError(RIOT_KEY_MISSING_MESSAGE)

    def get_rank(self, puuid: str) -> Optional[RankInfo]:
        raise NotImplementedError(RIOT_KEY_MISSING_MESSAGE)

    def has_ranked_solo_history(self, puuid: str) -> bool:
        raise NotImplementedError(RIOT_KEY_MISSING_MESSAGE)

    def get_match_history(self, puuid: str, count: int = 20, start: int = 0) -> list[MatchHistoryEntry]:
        raise NotImplementedError(RIOT_KEY_MISSING_MESSAGE)

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


class RiotAPIError(requests.HTTPError):
    """A non-2xx Riot API response, carrying an operator-readable Korean
    reason instead of requests' raw "403 Client Error: Forbidden for url"
    text - which is what the UI used to show, giving no hint that the real
    cause is usually an expired 24h development key. Still an HTTPError,
    so every existing `except requests.exceptions.RequestException`
    (position inference, refresh) keeps treating it the same way."""

    def __init__(self, status_code: int, response: requests.Response | None = None) -> None:
        self.status_code = status_code
        super().__init__(riot_error_message(status_code), response=response)


def riot_error_message(status_code: int) -> str:
    if status_code in (401, 403):
        return (
            "Riot API 키가 만료되었거나 유효하지 않습니다 - 서버 관리 → Riot API 키에서 새 키를 저장해주세요. "
            "(개발용 키는 발급 후 24시간마다 만료됩니다)"
        )
    if status_code == 404:
        return "해당 Riot ID를 찾을 수 없습니다 - 게임 이름과 태그(# 뒤)를 확인해주세요."
    if status_code == 429:
        return "Riot API 호출 한도를 초과했습니다 - 잠시 후 다시 시도해주세요."
    if status_code >= 500:
        return f"Riot API 서버 오류입니다 (상태 코드 {status_code}) - 잠시 후 다시 시도해주세요."
    return f"Riot API 요청이 실패했습니다 (상태 코드 {status_code})."


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
        # time.monotonic() value after which no new request is started -
        # set by callers running inside a serverless request (see
        # PlayerService.infer_position). None means no limit.
        self.deadline: Optional[float] = None

    def _seconds_left(self) -> Optional[float]:
        return None if self.deadline is None else self.deadline - time.monotonic()

    def _get(self, url: str) -> dict | list:
        for attempt in range(self.RATE_LIMIT_MAX_RETRIES + 1):
            seconds_left = self._seconds_left()
            if seconds_left is not None and seconds_left <= 0:
                raise RiotTimeBudgetExceeded("Riot API time budget exhausted")
            response = requests.get(url, headers={"X-Riot-Token": self.api_key}, timeout=10)
            if response.status_code == 429 and attempt < self.RATE_LIMIT_MAX_RETRIES:
                try:
                    wait_seconds = float(response.headers.get("Retry-After", self.RATE_LIMIT_DEFAULT_WAIT_SECONDS))
                except ValueError:
                    wait_seconds = self.RATE_LIMIT_DEFAULT_WAIT_SECONDS
                seconds_left = self._seconds_left()
                if seconds_left is not None and wait_seconds >= seconds_left:
                    # Waiting out the rate limit would overrun the budget -
                    # fail now rather than get killed mid-sleep.
                    raise RiotAPIError(429, response=response)
                time.sleep(wait_seconds)
                continue
            try:
                response.raise_for_status()
            except requests.HTTPError as exc:
                raise RiotAPIError(response.status_code, response=response) from exc
            return response.json()
        raise AssertionError("unreachable")  # loop always returns or raises on its final iteration

    def check_api_key(self) -> None:
        """Raises RiotAPIError if the key is rejected. Uses the platform
        status endpoint: it needs a valid key but no particular account,
        so an expired development key shows up without a real lookup."""
        self._get(f"https://{self.platform}.api.riotgames.com/lol/status/v4/platform-data")

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
            try:
                detail = self._get(detail_url)
            except RiotTimeBudgetExceeded:
                # Out of time mid-batch: the games already read are still a
                # valid (smaller) sample - return them instead of nothing.
                if entries:
                    return entries
                raise
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


def resolve_riot_api_key(session: Session | None = None) -> str | None:
    """The key saved on the 서버 관리 page (app_settings table) wins over
    the RIOT_API_KEY env var - a DB value survives serverless cold starts
    and changes without a redeploy, which an env var doesn't."""
    if session is not None:
        from app.database.repositories.app_setting_repository import RIOT_API_KEY, AppSettingRepository

        stored = AppSettingRepository(session).get(RIOT_API_KEY)
        if stored:
            return stored
    return settings.riot_api_key


def build_riot_client(session: Session | None = None) -> RiotAPIClient:
    """DI entry point: returns a working client if a Riot API key is
    configured (see resolve_riot_api_key), otherwise a client that fails
    loudly on first use."""
    api_key = resolve_riot_api_key(session)
    if not api_key:
        return NotImplementedRiotAPIClient()
    return LiveRiotAPIClient(
        api_key=api_key,
        platform=settings.riot_platform,
        region=settings.riot_region,
    )
