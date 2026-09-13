from __future__ import annotations

import io

import pandas as pd
import pytest

from app.roster_import import UnsupportedRosterFileError, parse_roster_file


def _csv_bytes(text: str) -> bytes:
    return text.encode("utf-8")


def test_csv_with_explicit_english_columns():
    csv = _csv_bytes("nickname,game_name,tag_line\n박찬학,한아른,담배연기\n한성민,제병철,0912\n")

    rows = parse_roster_file(csv, "roster.csv")

    assert len(rows) == 2
    assert rows[0].nickname == "박찬학"
    assert rows[0].game_name == "한아른"
    assert rows[0].tag_line == "담배연기"
    assert rows[1].game_name == "제병철"
    assert rows[1].tag_line == "0912"


def test_csv_with_explicit_korean_split_columns():
    # unambiguous - no '#' involved anywhere, so "닉네임" safely means
    # nickname here (game_name/tag_line are already their own columns).
    csv = _csv_bytes("닉네임,게임이름,태그\n허재혁,플루오린,0217\n")

    rows = parse_roster_file(csv, "roster.csv")

    assert len(rows) == 1
    assert rows[0].nickname == "허재혁"
    assert rows[0].game_name == "플루오린"
    assert rows[0].tag_line == "0217"


def test_csv_matching_the_real_ambiguous_header_layout():
    """Regression case for this app's own real user data: a spreadsheet
    with headers "이름"/"닉네임" where "닉네임" actually holds the combined
    Riot ID ("게임이름#태그"), not the nickname - the opposite of what the
    header name suggests in isolation. Content (the '#') must decide, not
    the header text."""
    csv = _csv_bytes("이름,닉네임\n허재혁,플루오린#0217\n강민수,KIRBY#ROK\n")

    rows = parse_roster_file(csv, "roster.csv")

    assert len(rows) == 2
    assert rows[0].nickname == "허재혁"
    assert rows[0].game_name == "플루오린"
    assert rows[0].tag_line == "0217"
    assert rows[1].nickname == "강민수"
    assert rows[1].game_name == "KIRBY"
    assert rows[1].tag_line == "ROK"


def test_csv_with_only_a_riot_id_column_defaults_nickname_to_game_name():
    csv = _csv_bytes("riot_id\nHideonbush#KR1\n")

    rows = parse_roster_file(csv, "roster.csv")

    assert len(rows) == 1
    assert rows[0].nickname == "Hideonbush"
    assert rows[0].game_name == "Hideonbush"
    assert rows[0].tag_line == "KR1"


def test_csv_rows_missing_a_hash_are_skipped_not_guessed():
    csv = _csv_bytes("이름,닉네임\n허재혁,플루오린#0217\n비어있음,그냥텍스트\n")

    rows = parse_roster_file(csv, "roster.csv")

    assert len(rows) == 1
    assert rows[0].nickname == "허재혁"


def test_txt_file_with_tab_delimiter():
    txt = "nickname\tgame_name\ttag_line\n박찬학\t한아른\t담배연기\n".encode("utf-8")

    rows = parse_roster_file(txt, "roster.txt")

    assert len(rows) == 1
    assert rows[0].nickname == "박찬학"
    assert rows[0].tag_line == "담배연기"


def test_xlsx_file():
    df = pd.DataFrame([{"nickname": "박찬학", "game_name": "한아른", "tag_line": "담배연기"}])
    buffer = io.BytesIO()
    df.to_excel(buffer, index=False)

    rows = parse_roster_file(buffer.getvalue(), "roster.xlsx")

    assert len(rows) == 1
    assert rows[0].nickname == "박찬학"
    assert rows[0].game_name == "한아른"
    assert rows[0].tag_line == "담배연기"


def test_unsupported_extension_raises():
    with pytest.raises(UnsupportedRosterFileError):
        parse_roster_file(b"whatever", "roster.pdf")


def test_no_resolvable_riot_id_column_raises():
    csv = _csv_bytes("이름,비고\n허재혁,관리자\n")

    with pytest.raises(UnsupportedRosterFileError):
        parse_roster_file(csv, "roster.csv")


def test_empty_file_returns_no_rows():
    csv = _csv_bytes("nickname,game_name,tag_line\n")

    assert parse_roster_file(csv, "roster.csv") == []


def test_txt_with_inconsistent_header_and_space_separated_data_lines():
    """Regression test for a real user file: the header line uses '/'
    ("이름/닉네임") but every data line uses a plain space
    ("허재혁 플루오린#0217"), with blank lines between entries. Sniffing a
    delimiter from this (pandas' sep=None/engine="python" picked '/' from
    the header alone, which doesn't apply to any data line) used to dump
    every data row into a single column and leave the second column
    entirely empty - nickname ended up as the whole unsplit
    "허재혁 플루오린#0217" instead of just "허재혁". Neither ',' nor '\t'
    appears anywhere in this file, so it must fall through to the
    per-line whitespace parser instead."""
    txt = (
        "이름/닉네임\n"
        "\n"
        "허재혁 플루오린#0217\n"
        "\n"
        "강민수 KIRBY#ROK\n"
        "\n"
        "박준용 박준용#박준용\n"
        "\n"
        "배민창 ξςεχψ#777\n"
    ).encode("utf-8")

    rows = parse_roster_file(txt, "roster.txt")

    assert len(rows) == 4
    assert rows[0].nickname == "허재혁"
    assert rows[0].game_name == "플루오린"
    assert rows[0].tag_line == "0217"
    assert rows[1].nickname == "강민수"
    assert rows[1].game_name == "KIRBY"
    assert rows[1].tag_line == "ROK"
    assert rows[2].nickname == "박준용"
    assert rows[2].game_name == "박준용"
    assert rows[2].tag_line == "박준용"
    assert rows[3].nickname == "배민창"
    assert rows[3].game_name == "ξςεχψ"
    assert rows[3].tag_line == "777"


def test_txt_free_form_parser_skips_lines_with_no_hash_token():
    txt = "이름/닉네임\n허재혁 플루오린#0217\n메모: 여기까지 등록 완료\n".encode("utf-8")

    rows = parse_roster_file(txt, "roster.txt")

    assert len(rows) == 1
    assert rows[0].nickname == "허재혁"
