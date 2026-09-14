from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.opgg.client import LiveOpggClient


def _response(text: str = "<html></html>") -> MagicMock:
    response = MagicMock(status_code=200, text=text)
    response.raise_for_status.return_value = None
    return response


def test_get_season_history_percent_encodes_the_name_and_tag():
    """Regression test: game_name/tag_line used to be dropped straight into
    the OP.GG URL unescaped via a plain f-string. A space in the name
    (extremely common - e.g. 'Hide on bush') or a Korean custom tag (this
    app explicitly supports Hangul tags in bulk OCR registration) is not a
    valid raw URL path segment, so an unescaped lookup risks silently
    404ing as "no Peak Tier data" for an account that actually has OP.GG
    history. Also strips incidental whitespace from copy-pasting."""
    client = LiveOpggClient()

    with patch("app.opgg.client.requests.get", return_value=_response()) as mock_get:
        client.get_season_history(" Hide on bush ", " 가나다 ")

    called_url = mock_get.call_args[0][0]
    assert "Hide on bush" not in called_url
    assert "Hide%20on%20bush" in called_url
    assert "%EA%B0%80%EB%82%98%EB%8B%A4" in called_url  # percent-encoded UTF-8 for 가나다
