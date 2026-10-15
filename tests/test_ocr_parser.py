from __future__ import annotations

from app.ocr.parser import (
    cluster_rows,
    detect_winning_team,
    extract_detail_stats,
    parse_detections_into_riot_ids,
    parse_rows_into_players,
)


def _box(x: float, y: float, w: float = 40, h: float = 20) -> list[list[float]]:
    return [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]


def test_cluster_rows_groups_by_y_and_sorts_by_x():
    detections = [
        (_box(100, 200), "3/5/7", 0.9),
        (_box(10, 202), "PlayerA", 0.9),
        (_box(50, 500), "1/2/3", 0.9),
        (_box(10, 498), "PlayerB", 0.9),
    ]

    rows = cluster_rows(detections, image_height=1000)

    assert len(rows) == 2
    assert [text for _, text in rows[0]] == ["PlayerA", "3/5/7"]
    assert [text for _, text in rows[1]] == ["PlayerB", "1/2/3"]


# --- cluster_rows: re-joining a Hangul name Tesseract split into one box
# per syllable (verified directly against a real participant-roster
# screenshot run through Tesseract - see app/ocr/parser.py's
# _merge_split_hangul docstring) ---


def test_cluster_rows_merges_adjacent_hangul_syllables_with_a_tight_gap():
    # "허재혁" detected as three separate one-syllable boxes 2px apart -
    # height 20 means anything under 12px (0.6 * height) is treated as the
    # same word, not a real gap between columns.
    detections = [
        (_box(10, 100, w=20), "허", 0.9),
        (_box(32, 100, w=20), "재", 0.9),
        (_box(54, 100, w=20), "혁", 0.9),
    ]

    rows = cluster_rows(detections, image_height=1000)

    assert [text for _, text in rows[0]] == ["허재혁"]


def test_cluster_rows_does_not_merge_hangul_across_a_real_column_gap():
    # same syllables, but 50px apart (a real column boundary, not kerning).
    detections = [
        (_box(10, 100, w=20), "허", 0.9),
        (_box(80, 100, w=20), "재", 0.9),
    ]

    rows = cluster_rows(detections, image_height=1000)

    assert [text for _, text in rows[0]] == ["허", "재"]


def test_cluster_rows_does_not_merge_hangul_into_a_riot_id_tag():
    # the Riot ID tag box ("#0217") must stay separate even with a tight
    # gap, so _split_riot_id can still find the '#' on its own box.
    detections = [
        (_box(10, 100, w=20), "린", 0.9),
        (_box(32, 100, w=30), "#0217", 0.9),
    ]

    rows = cluster_rows(detections, image_height=1000)

    assert [text for _, text in rows[0]] == ["린", "#0217"]


def test_parse_rows_extracts_kda_and_matches_known_nickname():
    rows = [
        [(0, "PlayerA"), (100, "5/2/8")],
        [(0, "PlayerB"), (100, "1/9/0")],
    ]

    parsed = parse_rows_into_players(rows, known_nicknames=["PlayerA", "PlayerB"])

    assert len(parsed) == 2
    assert parsed[0].raw_name == "PlayerA"
    assert (parsed[0].kills, parsed[0].deaths, parsed[0].assists) == (5, 2, 8)
    assert parsed[1].raw_name == "PlayerB"
    assert (parsed[1].kills, parsed[1].deaths, parsed[1].assists) == (1, 9, 0)


def test_parse_rows_falls_back_to_raw_text_when_no_nickname_matches():
    rows = [[(0, "xX_Weird0CRnoise_Xx"), (100, "3/3/3")]]

    parsed = parse_rows_into_players(rows, known_nicknames=["CompletelyDifferentName"])

    assert parsed[0].raw_name == "xX_Weird0CRnoise_Xx 3/3/3"
    assert parsed[0].matched_player_id is None


def test_parse_rows_assigns_team_index_by_position_in_first_five():
    rows = [[(0, f"P{i}"), (100, "1/1/1")] for i in range(10)]

    parsed = parse_rows_into_players(rows, known_nicknames=[f"P{i}" for i in range(10)])

    assert [p.team_index for p in parsed[:5]] == [0] * 5
    assert [p.team_index for p in parsed[5:]] == [1] * 5


def test_detect_winning_team_finds_victory_label_in_top_block():
    rows = [
        [(0, "승리")],
        [(0, "PlayerA"), (100, "5/2/8")],
        [(0, "패배")],
        [(0, "PlayerB"), (100, "1/9/0")],
    ]
    # 5 rows per team assumption means index-based split only kicks in over
    # PLAYERS_PER_TEAM rows; with a short synthetic list every row before
    # index 5 counts as team 0.
    assert detect_winning_team(rows) == 0


def test_detect_winning_team_returns_none_when_no_label_found():
    rows = [[(0, "PlayerA"), (100, "5/2/8")]]
    assert detect_winning_team(rows) is None


# --- Regression test built from a real Korean-client scoreboard screenshot ---
# (nicknames/values transcribed verbatim from the actual result screen; this
# validates the parser against real layout quirks: a "1번 팀"/"2번 팀" header
# row that itself contains a KDA-shaped aggregate, and comma-formatted gold.)
_REAL_SCOREBOARD_ROWS = [
    [(50, "코신 다리"), (200, "무작위 총력전: 아수라장"), (400, "20:15")],
    [(50, "1번 팀"), (200, "51 / 51 / 123"), (400, "97,436")],
    [(50, "18"), (100, "마스터 보내줘요"), (300, "18 / 8 / 25"), (450, "21,141")],
    [(50, "18"), (100, "커피엔담배"), (300, "12 / 9 / 30"), (450, "21,650")],
    [(50, "18"), (100, "채 은"), (300, "8 / 12 / 19"), (450, "17,759")],
    [(50, "18"), (100, "Thug"), (300, "7 / 9 / 21"), (450, "18,645")],
    [(50, "18"), (100, "브론즈탈출하고싶어요"), (300, "6 / 13 / 28"), (450, "18,241")],
    [(50, "2번 팀"), (200, "50 / 51 / 129"), (400, "94,045")],
    [(50, "18"), (100, "센트럴도그마"), (300, "11 / 11 / 21"), (450, "18,864")],
    [(50, "18"), (100, "로보냥"), (300, "12 / 14 / 25"), (450, "18,883")],
    [(50, "18"), (100, "햇참쌀떡"), (300, "6 / 10 / 34"), (450, "18,012")],
    [(50, "18"), (100, "Peace"), (300, "4 / 4 / 34"), (450, "17,838")],
    [(50, "18"), (100, "마 시"), (300, "17 / 12 / 15"), (450, "20,448")],
]

_REAL_NICKNAMES = [
    "마스터 보내줘요",
    "커피엔담배",
    "채 은",
    "Thug",
    "브론즈탈출하고싶어요",
    "센트럴도그마",
    "로보냥",
    "햇참쌀떡",
    "Peace",
    "마 시",
]


def test_real_scoreboard_skips_team_header_kda_and_uses_it_as_boundary():
    parsed = parse_rows_into_players(_REAL_SCOREBOARD_ROWS, _REAL_NICKNAMES)

    # the "51 / 51 / 123" team aggregate must NOT show up as a player row
    assert len(parsed) == 10
    assert [p.team_index for p in parsed] == [0] * 5 + [1] * 5


def test_real_scoreboard_extracts_gold_and_kda_correctly():
    parsed = parse_rows_into_players(_REAL_SCOREBOARD_ROWS, _REAL_NICKNAMES)

    first, last = parsed[0], parsed[-1]
    assert first.raw_name == "마스터 보내줘요"
    assert (first.kills, first.deaths, first.assists) == (18, 8, 25)
    assert first.gold == 21141

    assert last.raw_name == "마 시"
    assert (last.kills, last.deaths, last.assists) == (17, 12, 15)
    assert last.gold == 20448


def test_real_scoreboard_matches_all_ten_nicknames():
    parsed = parse_rows_into_players(_REAL_SCOREBOARD_ROWS, _REAL_NICKNAMES)
    assert [p.raw_name for p in parsed] == _REAL_NICKNAMES


def test_extract_detail_stats_includes_kda_join_key_in_whatever_column_order_it_appears():
    # deliberately NOT in the same order as the main scoreboard, mirroring
    # what was observed against a real screenshot pair
    detail_rows = [
        [(0, "KDA")]
        + [
            (50 + i * 40, v)
            for i, v in enumerate(
                ["6/13/28", "7/9/21", "18/8/25", "8/12/19", "12/9/30", "11/11/21", "12/14/25", "6/10/34", "4/4/34", "17/12/15"]
            )
        ],
        [(0, "미니언 처치")] + [(50 + i * 40, str(v)) for i, v in enumerate([39, 68, 94, 18, 23, 43, 63, 17, 35, 60])],
    ]

    stats = extract_detail_stats(detail_rows)

    assert stats["kda"][0] == (6, 13, 28)
    assert stats["kda"][2] == (18, 8, 25)
    assert stats["cs"][2] == 94  # same column position as the (18,8,25) KDA


def test_extract_detail_stats_reads_cs_row_by_label_prefix():
    detail_rows = [
        [(0, "미니언 처치")] + [(50 + i * 40, str(v)) for i, v in enumerate([39, 68, 94, 18, 23, 43, 63, 17, 35, 60])],
        [(0, "챔피언에게 가한 물리 피해량")] + [(50 + i * 40, "999") for i in range(10)],
        [(0, "챔피언에게 가한 피해량")]
        + [
            (50 + i * 40, v)
            for i, v in enumerate(
                ["76,904", "38,673", "125,598", "25,310", "24,103", "43,984", "51,485", "18,722", "32,756", "68,726"]
            )
        ],
    ]

    stats = extract_detail_stats(detail_rows)

    assert stats["cs"] == [39, 68, 94, 18, 23, 43, 63, 17, 35, 60]
    assert stats["damage"] == [76904, 38673, 125598, 25310, 24103, 43984, 51485, 18722, 32756, 68726]


# --- parse_detections_into_riot_ids: participant-roster screenshots ---
# Layout and word splits mirror a real spreadsheet capture run through
# Google Vision: nickname | Riot ID | current tier | peak tier | main | sub,
# with Vision splitting a Riot ID into several word boxes ("플루오", "린",
# "#", "0217") - looking for one box holding the whole ID lost most rows.

TEXT_H = 14


def _row(y: float, *words: tuple[str, float, float]) -> list:
    """words: (text, left, width) at the same y."""
    return [(_box(left, y, w=width, h=TEXT_H), text, 1.0) for text, left, width in words]


def _tier_and_role_columns(y: float) -> list:
    return _row(y, ("다이아", 197, 30), ("1", 228, 6), ("다이아", 255, 30), ("4", 286, 6), ("정글", 320, 24), ("탑", 375, 12))


def test_riot_id_split_into_several_vision_words_is_rejoined():
    detections = _row(10, ("허재혁", 12, 36), ("플루오", 95, 36), ("린", 131, 12), ("#", 143, 8), ("0217", 151, 28))
    detections += _tier_and_role_columns(10)

    [row] = parse_detections_into_riot_ids(detections)

    assert (row.nickname, row.game_name, row.tag_line) == ("허재혁", "플루오린", "0217")


def test_other_columns_never_leak_into_the_nickname():
    detections = _row(10, ("강민수", 12, 36), ("KIRBY", 95, 40), ("#ROK", 135, 30)) + _tier_and_role_columns(10)

    [row] = parse_detections_into_riot_ids(detections)

    assert row.nickname == "강민수"
    assert (row.game_name, row.tag_line) == ("KIRBY", "ROK")


def test_real_spaces_inside_a_game_name_are_kept():
    detections = _row(
        10, ("신재원", 12, 36), ("Hasta", 95, 30), ("La", 130, 12), ("Vista", 147, 28), ("#", 175, 8), ("more", 183, 24)
    )

    [row] = parse_detections_into_riot_ids(detections)

    assert (row.game_name, row.tag_line) == ("Hasta La Vista", "more")


def test_korean_custom_tag_is_accepted():
    # Riot's KR server allows an arbitrary Hangul tag ("한아른#담배연기" is
    # a real account verified against the live Riot API).
    detections = _row(10, ("박찬학", 12, 36), ("한아", 95, 24), ("른", 119, 12), ("#", 131, 8), ("담배", 139, 24), ("연기", 163, 24))

    [row] = parse_detections_into_riot_ids(detections)

    assert (row.nickname, row.game_name, row.tag_line) == ("박찬학", "한아른", "담배연기")


def test_nickname_split_into_syllable_boxes_is_rejoined():
    detections = _row(10, ("구동", 12, 24), ("하", 36, 12), ("오라", 95, 24), ("#EVA", 119, 30))

    [row] = parse_detections_into_riot_ids(detections)

    assert row.nickname == "구동하"


def test_row_where_ocr_missed_the_hash_is_kept_from_the_riot_id_column():
    detections = _row(10, ("허재혁", 12, 36), ("플루오린#0217", 95, 60)) + _tier_and_role_columns(10)
    detections += _row(40, ("이찬우", 12, 36), ("건전지", 95, 36), ("KR1", 136, 24)) + _tier_and_role_columns(40)

    rows = parse_detections_into_riot_ids(detections)

    assert [(r.nickname, r.game_name, r.tag_line) for r in rows] == [
        ("허재혁", "플루오린", "0217"),
        ("이찬우", "건전지", "KR1"),
    ]


def test_every_row_of_a_multi_row_roster_is_read():
    names = ["허재혁", "강민수", "김경태", "최원준", "권명"]
    detections = []
    for i, name in enumerate(names):
        y = 10 + i * 20  # ~20px row pitch, same as the real capture
        detections += _row(y, (name, 12, 36), (f"게임{i}", 95, 30), ("#", 125, 8), ("KR1", 133, 24))
        detections += _tier_and_role_columns(y)

    rows = parse_detections_into_riot_ids(detections)

    assert [r.nickname for r in rows] == names
    assert all(r.tag_line == "KR1" for r in rows)


def test_nickname_defaults_to_game_name_when_there_is_no_name_column():
    [row] = parse_detections_into_riot_ids(_row(10, ("Hideonbush#KR1", 12, 90)))

    assert (row.nickname, row.game_name, row.tag_line) == ("Hideonbush", "Hideonbush", "KR1")


def test_captions_and_rows_without_a_riot_id_are_skipped():
    detections = _row(10, ("참가자 명단", 12, 80))
    detections += _row(40, ("임도현", 12, 36), ("Hideonbush#KR1", 95, 90))

    rows = parse_detections_into_riot_ids(detections)

    assert [r.nickname for r in rows] == ["임도현"]


def test_no_riot_ids_at_all_returns_nothing():
    assert parse_detections_into_riot_ids(_row(10, ("그냥", 12, 30), ("텍스트", 60, 40))) == []


def test_tier_column_glued_onto_a_long_riot_id_is_cut_off():
    # "서울대분노조절학과#gnar" runs right up to the tier column, so OCR
    # joins the two with no visible gap.
    detections = _row(
        10, ("김동규", 12, 36), ("서울대분노조절학과", 95, 80), ("#gnar", 175, 20), ("에메", 196, 24), ("3", 221, 6)
    )
    detections += _row(40, ("최병관", 12, 36), ("미크로파키케팔로사우르스", 95, 100), ("다이아", 196, 30), ("4", 227, 6), ("미드", 320, 24))

    rows = parse_detections_into_riot_ids(detections)

    assert [(r.game_name, r.tag_line) for r in rows] == [
        ("서울대분노조절학과", "gnar"),
        ("미크로파키케팔로사우르스", ""),  # '#tag' cut off in the capture itself - left for review
    ]
