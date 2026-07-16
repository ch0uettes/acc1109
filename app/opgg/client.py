from __future__ import annotations

from abc import ABC, abstractmethod

import requests

from app.opgg.parser import parse_season_history_html
from app.opgg.schemas import SeasonTierEntry

OPGG_SOURCE_LABEL = "OP.GG"


class OpggClient(ABC):
    """Interface for OP.GG's season-by-season rank history lookup - the one
    thing this app needs that Riot's own API doesn't expose (League-V4 only
    ever returns the CURRENT season's rank; there is no past-season-history
    endpoint), which is why Peak Tier previously had to be entered by hand
    every time. Data via OP.GG (https://op.gg) - per OP.GG's own Help
    Center ("Can I use OP.GG data?"), crawling is permitted with source
    attribution and without excessive request volume; this is a single
    lookup per player registration, well within that.

    Kept independent of any one HTTP/parsing implementation, same seam
    philosophy as RiotAPIClient/OCRExtractor - a page-layout change on
    OP.GG's end should only ever require touching LiveOpggClient (or, more
    precisely, app/opgg/parser.py), never any caller."""

    @abstractmethod
    def get_season_history(self, game_name: str, tag_line: str, platform: str = "kr") -> list[SeasonTierEntry]:
        """Empty list if OP.GG has no ranked season history for this Riot
        ID at all (e.g. a genuinely new/never-ranked account) - never None,
        so callers can treat "no history" and "found zero rows" the same
        way."""


class NotImplementedOpggClient(OpggClient):
    """Bound when 'beautifulsoup4' isn't installed. Fails loudly instead of
    silently, matching NotImplementedRiotAPIClient/NotImplementedOCRExtractor."""

    def get_season_history(self, game_name: str, tag_line: str, platform: str = "kr") -> list[SeasonTierEntry]:
        raise NotImplementedError(
            "OP.GG lookup is not available - install 'beautifulsoup4' (pip install -r requirements.txt) to enable it"
        )


class LiveOpggClient(OpggClient):
    """Scrapes OP.GG's summoner profile page for its season-history table.
    Confirmed the table is present in the plain server-rendered HTML (no JS
    execution/headless browser needed) - a normal HTTP GET + HTML parse is
    enough. Best-effort like the OCR pipeline: OP.GG can change its page
    layout at any time with zero notice, so every caller of this class
    treats a failure here (network error, HTTP error, or the season table
    simply not being found on the page - see parse_season_history_html) as
    "no Peak Tier data available", never as something that blocks or
    crashes player registration."""

    BASE_URL = "https://op.gg/lol/summoners"
    REQUEST_TIMEOUT_SECONDS = 10
    # Locks the page to English column headers ("Season"/"Tier"/"LP")
    # regardless of any server-side geolocation-based language guess -
    # parse_season_history_html matches on those exact header strings.
    _HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }

    def get_season_history(self, game_name: str, tag_line: str, platform: str = "kr") -> list[SeasonTierEntry]:
        url = f"{self.BASE_URL}/{platform}/{game_name}-{tag_line}"
        response = requests.get(url, headers=self._HEADERS, timeout=self.REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        return parse_season_history_html(response.text)


def build_opgg_client() -> OpggClient:
    try:
        import bs4  # noqa: F401
    except ImportError:
        return NotImplementedOpggClient()
    return LiveOpggClient()
