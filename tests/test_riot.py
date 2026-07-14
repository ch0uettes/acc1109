from __future__ import annotations

from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

import pytest

from app.riot.client import (
    CHALLENGER_LP_OFFSET,
    GRANDMASTER_LP_OFFSET,
    LiveRiotAPIClient,
    _convert_riot_rank,
)
from app.utils.enums import Division, Tier


def test_convert_normal_tier_keeps_division_and_lp():
    tier, division, lp = _convert_riot_rank("GOLD", "II", 45)
    assert tier == Tier.GOLD
    assert division == Division.II
    assert lp == 45


def test_convert_master_uses_lp_as_is():
    tier, division, lp = _convert_riot_rank("MASTER", "I", 120)
    assert tier == Tier.MASTER
    assert lp == 120


def test_convert_grandmaster_offsets_lp_above_master():
    tier, division, lp = _convert_riot_rank("GRANDMASTER", "I", 50)
    assert tier == Tier.MASTER
    assert lp == 50 + GRANDMASTER_LP_OFFSET


def test_convert_challenger_offsets_lp_above_grandmaster():
    _, _, gm_lp = _convert_riot_rank("GRANDMASTER", "I", 999)
    _, _, challenger_lp = _convert_riot_rank("CHALLENGER", "I", 0)
    assert challenger_lp > gm_lp
    assert challenger_lp == CHALLENGER_LP_OFFSET


def test_has_ranked_solo_history_true_when_match_ids_returned():
    client = LiveRiotAPIClient(api_key="fake-key")
    fake_response = MagicMock(ok=True)
    fake_response.json.return_value = ["KR_1"]

    with patch("app.riot.client.requests.get", return_value=fake_response):
        assert client.has_ranked_solo_history("some-puuid") is True


def test_has_ranked_solo_history_false_when_no_matches():
    client = LiveRiotAPIClient(api_key="fake-key")
    fake_response = MagicMock(ok=True)
    fake_response.json.return_value = []

    with patch("app.riot.client.requests.get", return_value=fake_response):
        assert client.has_ranked_solo_history("some-puuid") is False


def _fake_match_detail(puuid: str, team_position: str, champion: str = "Ahri", win: bool = True) -> dict:
    return {
        "info": {
            "participants": [
                {"puuid": "other-puuid", "teamPosition": "TOP", "championName": "Garen", "win": not win},
                {"puuid": puuid, "teamPosition": team_position, "championName": champion, "win": win},
            ]
        }
    }


def _mock_get_for(puuid: str, positions_by_match: dict[str, str]):
    """Builds a requests.get stand-in: the /ids endpoint paginates over the
    match id keys using the URL's start/count params (mirroring real
    Match-V5 pagination), and each match detail endpoint returns that
    match's teamPosition."""
    all_ids = list(positions_by_match.keys())

    def _get(url: str, headers=None, timeout=None):
        response = MagicMock(ok=True)
        if "/ids" in url:
            query = parse_qs(urlparse(url).query)
            start = int(query.get("start", ["0"])[0])
            count = int(query.get("count", ["20"])[0])
            response.json.return_value = all_ids[start : start + count]
        else:
            match_id = url.rsplit("/", 1)[-1]
            response.json.return_value = _fake_match_detail(puuid, positions_by_match[match_id])
        return response

    return _get


def test_get_match_history_maps_team_position_to_domain_position():
    puuid = "some-puuid"
    positions = {"KR_1": "MIDDLE", "KR_2": "BOTTOM"}
    client = LiveRiotAPIClient(api_key="fake-key")

    with patch("app.riot.client.requests.get", side_effect=_mock_get_for(puuid, positions)):
        with patch("app.riot.client.time.sleep"):
            entries = client.get_match_history(puuid, count=2)

    assert [e.match_id for e in entries] == ["KR_1", "KR_2"]
    assert entries[0].position.value == "MID"
    assert entries[1].position.value == "ADC"
