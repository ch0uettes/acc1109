from __future__ import annotations

from app.opgg.parser import parse_season_history_html
from app.utils.enums import Division, Tier

# Trimmed but structurally faithful to a real OP.GG summoner page's season
# history table (verified against a live page during development - see
# app/opgg/client.py's docstrings). Only the one <table> with headers
# ["Season", "Tier", "LP"] should ever be parsed.
_SEASON_TABLE_HTML = """
<html><body>
<table><thead><tr><th>Unrelated</th><th>Table</th></tr></thead>
<tbody><tr><td>should be ignored</td><td>1/2/3</td></tr></tbody></table>
<table>
<thead><tr><th scope="col">Season</th><th scope="col">Tier</th><th scope="col">LP</th></tr></thead>
<tbody>
<tr><td><strong>S2025</strong></td><td><div><span>master</span></div></td><td align="right">285</td></tr>
<tr><td><strong>S2024 S3</strong></td><td><div><span>master</span></div></td><td align="right">83</td></tr>
<tr><td><strong>S2024 S2</strong></td><td><div><span>grandmaster</span></div></td><td align="right">1,066</td></tr>
<tr><td><strong>S2024 S1</strong></td><td><div><span>diamond 1</span></div></td><td align="right">40</td></tr>
</tbody>
</table>
</body></html>
"""


def test_parses_all_season_rows_from_the_season_table():
    entries = parse_season_history_html(_SEASON_TABLE_HTML)
    assert [e.season for e in entries] == ["S2025", "S2024 S3", "S2024 S2", "S2024 S1"]


def test_ignores_unrelated_tables_on_the_page():
    entries = parse_season_history_html(_SEASON_TABLE_HTML)
    assert all(e.season != "should be ignored" for e in entries)


def test_parses_plain_tier_without_division():
    entries = parse_season_history_html(_SEASON_TABLE_HTML)
    s2025 = next(e for e in entries if e.season == "S2025")
    assert s2025.tier == Tier.MASTER
    assert s2025.lp == 285


def test_parses_tier_with_division_number():
    entries = parse_season_history_html(_SEASON_TABLE_HTML)
    s2024_s1 = next(e for e in entries if e.season == "S2024 S1")
    assert s2024_s1.tier == Tier.DIAMOND
    assert s2024_s1.division == Division.I
    assert s2024_s1.lp == 40


def test_rebase_grandmaster_lp_onto_the_unified_master_scale():
    # Real-world regression: a Grandmaster season with 1,066 raw LP must
    # convert to Tier.MASTER with the GRANDMASTER_LP_OFFSET applied (see
    # app.riot.client._convert_riot_rank), not just 1,066 - otherwise it
    # would rank BELOW a long-established Master player's LP incorrectly.
    entries = parse_season_history_html(_SEASON_TABLE_HTML)
    gm_season = next(e for e in entries if e.season == "S2024 S2")
    assert gm_season.tier == Tier.MASTER
    assert gm_season.lp == 1066 + 1000  # GRANDMASTER_LP_OFFSET


def test_parses_comma_formatted_lp():
    entries = parse_season_history_html(_SEASON_TABLE_HTML)
    gm_season = next(e for e in entries if e.season == "S2024 S2")
    assert gm_season.lp == 2066  # "1,066" parsed correctly, not truncated at the comma


def test_returns_empty_list_when_no_season_table_present():
    html = "<html><body><table><thead><tr><th>Champion</th></tr></thead><tbody></tbody></table></body></html>"
    assert parse_season_history_html(html) == []


def test_returns_empty_list_for_an_empty_season_table():
    html = """
    <table><thead><tr><th>Season</th><th>Tier</th><th>LP</th></tr></thead><tbody></tbody></table>
    """
    assert parse_season_history_html(html) == []


def test_skips_malformed_rows_without_crashing():
    html = """
    <table>
    <thead><tr><th>Season</th><th>Tier</th><th>LP</th></tr></thead>
    <tbody>
    <tr><td><strong>S2025</strong></td><td><div><span>master</span></div></td><td>not-a-number</td></tr>
    <tr><td><strong>S2024</strong></td><td><div><span>gold 2</span></div></td><td>50</td></tr>
    </tbody>
    </table>
    """
    entries = parse_season_history_html(html)
    assert len(entries) == 1  # the not-a-number LP row was skipped, not crashed on
    assert entries[0].season == "S2024"
    assert entries[0].tier == Tier.GOLD
    assert entries[0].division == Division.II
