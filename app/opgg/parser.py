from __future__ import annotations

from app.opgg.schemas import SeasonTierEntry
from app.riot.client import _convert_riot_rank  # shared Tier/Division/lp normalization

# OP.GG's season history table spells division as an arabic numeral
# ("diamond 1") rather than Riot's own roman-numeral strings - map back to
# what _convert_riot_rank (and the rest of this app) expects.
_DIVISION_NUMBER_TO_ROMAN = {"1": "I", "2": "II", "3": "III", "4": "IV"}


def _parse_opgg_tier_text(text: str) -> tuple[str, str]:
    """"diamond 1" -> ("DIAMOND", "I"); "master" -> ("MASTER", "IV" - ignored
    by _convert_riot_rank for Master+ anyway)."""
    parts = text.strip().split()
    tier_word = parts[0].upper()
    division = _DIVISION_NUMBER_TO_ROMAN.get(parts[1], "IV") if len(parts) > 1 else "IV"
    return tier_word, division


def parse_season_history_html(html: str) -> list[SeasonTierEntry]:
    """Raw HTML -> season history rows. Split out from LiveOpggClient so the
    parsing logic (the part that actually breaks if OP.GG changes its page)
    is testable against a canned HTML string, with no network call - same
    "fetch vs parse" separation as app/ocr's _read_rows vs
    parse_rows_into_players.

    Scoped to the one <table> whose header row is exactly
    ["Season", "Tier", "LP"] (rather than matching any 3-column row
    anywhere on the page, which OP.GG's page has plenty of elsewhere -
    champion stat tables, etc.) - returns [] if that table isn't found at
    all, same as if it were found but empty."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    season_table = None
    for table in soup.find_all("table"):
        headers = [th.get_text(strip=True) for th in table.select("thead th")]
        if headers == ["Season", "Tier", "LP"]:
            season_table = table
            break
    if season_table is None:
        return []

    entries: list[SeasonTierEntry] = []
    for row in season_table.select("tbody tr"):
        cells = row.find_all("td")
        if len(cells) != 3:
            continue
        season_cell = cells[0].find("strong")
        tier_cell = cells[1].find("span")
        if season_cell is None or tier_cell is None:
            continue
        lp_text = cells[2].get_text(strip=True).replace(",", "")
        if not lp_text.isdigit():
            continue

        riot_tier, riot_division = _parse_opgg_tier_text(tier_cell.get_text(strip=True))
        try:
            tier, division, lp = _convert_riot_rank(riot_tier, riot_division, int(lp_text))
        except ValueError:
            continue  # unrecognized tier text (site changed?) - skip this row, not the whole page

        entries.append(SeasonTierEntry(season=season_cell.get_text(strip=True), tier=tier, division=division, lp=lp))

    return entries
