from __future__ import annotations

from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

import pytest
import requests

from app.riot.client import (
    CHALLENGER_LP_OFFSET,
    GRANDMASTER_LP_OFFSET,
    LiveRiotAPIClient,
    _convert_riot_rank,
)
from app.utils.enums import Division, Tier


def _response(status_code: int, payload=None, headers=None) -> MagicMock:
    response = MagicMock(status_code=status_code, headers=headers or {})
    response.json.return_value = payload
    if status_code >= 400:
        response.raise_for_status.side_effect = requests.HTTPError(response=response)
    else:
        response.raise_for_status.return_value = None
    return response


def test_get_retries_after_a_429_and_returns_the_eventual_success():
    """Regression test: a dev key's rate-limit window can fill up mid-batch
    (e.g. several players' position inference back to back during bulk
    registration - observed directly in production) and Riot's 429 tells
    us exactly how long to wait via Retry-After. One transient 429 must not
    surface as a crash if a retry within budget succeeds."""
    client = LiveRiotAPIClient(api_key="fake-key")
    responses = [_response(429, headers={"Retry-After": "0"}), _response(200, payload={"ok": True})]

    with patch("app.riot.client.requests.get", side_effect=responses):
        with patch("app.riot.client.time.sleep") as mock_sleep:
            result = client._get("https://example.invalid/x")

    assert result == {"ok": True}
    mock_sleep.assert_called_once_with(0.0)


def test_get_gives_up_after_max_retries_and_raises_the_final_429():
    client = LiveRiotAPIClient(api_key="fake-key")
    responses = [_response(429, headers={"Retry-After": "0"}) for _ in range(10)]

    with patch("app.riot.client.requests.get", side_effect=responses):
        with patch("app.riot.client.time.sleep"):
            with pytest.raises(requests.HTTPError):
                client._get("https://example.invalid/x")


def test_get_falls_back_to_a_default_wait_when_retry_after_is_missing_or_invalid():
    client = LiveRiotAPIClient(api_key="fake-key")
    responses = [_response(429, headers={}), _response(200, payload={"ok": True})]

    with patch("app.riot.client.requests.get", side_effect=responses):
        with patch("app.riot.client.time.sleep") as mock_sleep:
            client._get("https://example.invalid/x")

    mock_sleep.assert_called_once_with(LiveRiotAPIClient.RATE_LIMIT_DEFAULT_WAIT_SECONDS)


def test_get_account_by_riot_id_percent_encodes_the_name_and_tag():
    """Regression test: game_name/tag_line used to be dropped straight into
    the URL path unescaped. A space in the name (extremely common - e.g.
    'Hide on bush') or a Korean custom tag (this app explicitly supports
    Hangul tags in bulk OCR registration) is not a valid raw URL path
    segment, so an unescaped lookup risks silently 404ing as "player not
    found" for an account that actually exists. Also strips incidental
    whitespace from copy-pasting "Name #KR1"."""
    client = LiveRiotAPIClient(api_key="fake-key")
    response = _response(200, payload={"puuid": "p1", "gameName": "Hide on bush", "tagLine": "가나다"})

    with patch("app.riot.client.requests.get", return_value=response) as mock_get:
        client.get_account_by_riot_id(" Hide on bush ", " 가나다 ")

    called_url = mock_get.call_args[0][0]
    assert "Hide on bush" not in called_url  # unescaped space/text must not appear raw
    assert "Hide%20on%20bush" in called_url
    assert "%EA%B0%80%EB%82%98%EB%8B%A4" in called_url  # percent-encoded UTF-8 for 가나다


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


def test_get_match_history_skips_a_match_missing_the_queried_puuid():
    """Regression test: a match returned by this exact puuid's own /ids
    lookup can still come back from the detail endpoint without that
    puuid anywhere in its participants (a renamed/merged account whose
    historical match data still references an old puuid, or a data
    inconsistency right after the match completes - observed directly in
    production). next() with no default raised an uncaught StopIteration
    there, crashing position inference entirely instead of just skipping
    that one unreadable match."""
    puuid = "some-puuid"

    def _get(url: str, headers=None, timeout=None):
        response = MagicMock(ok=True)
        if "/ids" in url:
            response.json.return_value = ["KR_1", "KR_2"]
        elif url.endswith("KR_1"):
            # KR_1's detail data doesn't actually list `puuid` at all.
            response.json.return_value = {
                "info": {"participants": [{"puuid": "someone-else", "teamPosition": "TOP", "championName": "Garen", "win": True}]}
            }
        else:
            response.json.return_value = _fake_match_detail(puuid, "MIDDLE")
        return response

    client = LiveRiotAPIClient(api_key="fake-key")
    with patch("app.riot.client.requests.get", side_effect=_get):
        with patch("app.riot.client.time.sleep"):
            entries = client.get_match_history(puuid, count=2)

    assert [e.match_id for e in entries] == ["KR_2"]
    assert entries[0].position.value == "MID"
