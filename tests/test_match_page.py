from __future__ import annotations

from app.ui.pages.match_page import _is_stale_ocr, _match_detail_stats_by_kda


def test_new_match_combo_makes_previous_ocr_stale():
    """Match A's OCR was parsed under token A; team_page.py mints a new
    token B when a *different* combo (Match B) is saved - that must mark
    Match A's OCR data as stale so it never gets attributed to Match B."""
    assert _is_stale_ocr(ocr_parsed_token="token-A", current_match_token="token-B") is True


def test_revisiting_the_same_unsaved_match_preserves_its_ocr():
    """Navigating away and back (or a plain rerun) without team_page.py
    saving a new combo keeps the same match_context_token - OCR parsed for
    the still-current match must survive."""
    assert _is_stale_ocr(ocr_parsed_token="token-A", current_match_token="token-A") is False


def test_no_ocr_parsed_yet_is_not_treated_as_a_match():
    # Nothing uploaded yet this match context - no data to keep or drop.
    assert _is_stale_ocr(ocr_parsed_token=None, current_match_token="token-A") is True


def test_a_pre_token_combo_is_conservatively_treated_as_stale():
    # Defensive fallback: a combo saved before this token scheme existed in
    # this session (current_match_token missing) must not let old OCR data
    # silently carry over either.
    assert _is_stale_ocr(ocr_parsed_token="token-A", current_match_token=None) is True


def _participant(name: str, k: int, d: int, a: int) -> dict:
    return {"raw_name": name, "kills": k, "deaths": d, "assists": a}


def test_match_detail_stats_by_kda_assigns_unique_kda_correctly():
    participants = [_participant("Alice", 5, 2, 8), _participant("Bob", 1, 9, 0)]
    detail_stats = {"kda": [(1, 9, 0), (5, 2, 8)], "cs": [120, 200], "vision_score": [10, 20]}

    matched_count, ambiguous_names = _match_detail_stats_by_kda(participants, detail_stats)

    assert matched_count == 2
    assert ambiguous_names == []
    assert participants[0]["cs"] == 200 and participants[0]["vision_score"] == 20
    assert participants[1]["cs"] == 120 and participants[1]["vision_score"] == 10


def test_match_detail_stats_by_kda_never_guesses_between_two_players_sharing_a_kda():
    """Core invariant: a KDA shared by more than one participant must never
    be silently assigned to the wrong one - both stay unmatched and are
    reported as ambiguous instead."""
    participants = [_participant("SupportA", 0, 0, 0), _participant("SupportB", 0, 0, 0)]
    detail_stats = {"kda": [(0, 0, 0), (0, 0, 0)], "cs": [15, 999], "vision_score": [40, 5]}

    matched_count, ambiguous_names = _match_detail_stats_by_kda(participants, detail_stats)

    assert matched_count == 0
    assert set(ambiguous_names) == {"SupportA", "SupportB"}
    assert "cs" not in participants[0] and "cs" not in participants[1]


def test_match_detail_stats_by_kda_still_matches_unambiguous_players_alongside_a_duplicate_pair():
    participants = [
        _participant("SupportA", 0, 0, 0),
        _participant("SupportB", 0, 0, 0),
        _participant("Carry", 12, 1, 4),
    ]
    detail_stats = {"kda": [(0, 0, 0), (12, 1, 4), (0, 0, 0)], "cs": [15, 220, 12], "vision_score": [40, 8, 38]}

    matched_count, ambiguous_names = _match_detail_stats_by_kda(participants, detail_stats)

    assert matched_count == 1
    assert set(ambiguous_names) == {"SupportA", "SupportB"}
    assert participants[2]["cs"] == 220 and participants[2]["vision_score"] == 8
    assert "cs" not in participants[0] and "cs" not in participants[1]
