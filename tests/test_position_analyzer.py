from __future__ import annotations

from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

import pytest

from app.position.analyzer import RiotHistoryPositionAnalyzer
from app.riot.client import LiveRiotAPIClient


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


def _analyzer() -> RiotHistoryPositionAnalyzer:
    return RiotHistoryPositionAnalyzer(LiveRiotAPIClient(api_key="fake-key"))


def test_recommend_returns_none_with_no_history():
    with patch("app.riot.client.requests.get", side_effect=_mock_get_for("p", {})):
        with patch("app.riot.client.time.sleep"):
            assert _analyzer().recommend("p") is None


def test_recommend_confident_within_minimum_window_reports_main_and_sub():
    puuid = "p"
    # 15 MIDDLE + 5 BOTTOM out of the first 20 -> 75% ratio, clears the 60% bar
    positions = {f"KR_{i}": ("MIDDLE" if i < 15 else "BOTTOM") for i in range(20)}

    with patch("app.riot.client.requests.get", side_effect=_mock_get_for(puuid, positions)):
        with patch("app.riot.client.time.sleep"):
            recommendation = _analyzer().recommend(puuid)

    assert recommendation.main.value == "MID"
    assert recommendation.main_ratio == pytest.approx(0.75)
    assert recommendation.sub.value == "ADC"
    assert recommendation.sub_ratio == pytest.approx(0.25)
    assert recommendation.sample_size == 20


def test_recommend_widens_window_when_role_swaps_a_lot():
    puuid = "p"
    # first 20 matches: 50/50 split (not confident) -> should fetch 20 more
    positions = {f"KR_{i}": ("MIDDLE" if i % 2 == 0 else "BOTTOM") for i in range(20)}
    # next 20 matches: all MIDDLE, tips the cumulative ratio over 60%
    positions.update({f"KR_{i}": "MIDDLE" for i in range(20, 40)})

    with patch("app.riot.client.requests.get", side_effect=_mock_get_for(puuid, positions)):
        with patch("app.riot.client.time.sleep"):
            recommendation = _analyzer().recommend(puuid)

    assert recommendation.main.value == "MID"
    assert recommendation.main_ratio == pytest.approx(30 / 40)
    assert recommendation.sample_size == 40


def test_recommend_no_sub_when_only_one_position_ever_played():
    puuid = "p"
    positions = {f"KR_{i}": "MIDDLE" for i in range(20)}

    with patch("app.riot.client.requests.get", side_effect=_mock_get_for(puuid, positions)):
        with patch("app.riot.client.time.sleep"):
            recommendation = _analyzer().recommend(puuid)

    assert recommendation.main.value == "MID"
    assert recommendation.main_ratio == 1.0
    assert recommendation.sub is None
    assert recommendation.sub_ratio is None
