from __future__ import annotations

import re
import statistics
from dataclasses import dataclass
from difflib import get_close_matches
from typing import Optional

from app.ocr.schemas import OCRPlayerRow, OCRRiotIdRow

# OCR row grouping: LoL's end-game table lines are evenly spaced, so nearby
# detections are clustered into one row using a tolerance sized as a
# fraction of image height (not a fixed pixel count) so it holds up across
# different screenshot resolutions.
ROW_Y_TOLERANCE_RATIO = 0.015

PLAYERS_PER_TEAM = 5

_KDA_PATTERN = re.compile(r"(\d+)\s*/\s*(\d+)\s*/\s*(\d+)")
_GOLD_PATTERN = re.compile(r"\d{1,3}(?:,\d{3})+")
# The scoreboard splits teams with a team-number header row (which also
# carries that *team's* aggregate KDA - easy to mistake for a player row,
# so it's matched and skipped explicitly before anything else). Captures
# the team number itself so the caller can use it directly instead of a
# first-seen/not-first-seen toggle - see parse_rows_into_players.
#
# The real client text is "1 팀" / "2 팀" - no "번" - confirmed directly
# against real screenshots via both Tesseract and Google Vision. The
# previous pattern here required a literal "번" that never actually
# appears in this client's UI text, so header rows were never recognized
# at all: each one fell through to the KDA check below and got parsed as
# an 11th phantom "player" (its own team-aggregate KDA matching
# _KDA_PATTERN), which then threw off the positional 5-then-5 fallback
# split for every row after it - observed directly as a real participant
# (row 6, right after 5 legitimate rows) landing in the wrong team.
_TEAM_HEADER_PATTERN = re.compile(r"(?:^|\s)(\d+)\s*번?\s*팀(?!\S)")

# The detail/stat-comparison screenshot (CS, vision, damage, ...) has no
# player names at all - just one column per player in the same left-to-right,
# team-by-team order as the main scoreboard. Matching is done by prefix so
# e.g. "챔피언에게 가한 피해량" doesn't also match "챔피언에게 가한 물리 피해량".
STAT_LABELS: dict[str, str] = {
    "cs": "미니언 처치",
    "vision_score": "시야 점수",
    "damage": "챔피언에게 가한 피해량",
    "gold": "골드 획득",
}

# Riot ID tags used to always be a short alphanumeric region code ("KR1",
# "NA1", "1234"), but Riot's KR server also lets players pick an arbitrary
# custom Hangul tag - confirmed directly against this app's own real roster
# data (e.g. "한아른#담배연기" resolved fine through the live Riot API) - so
# the tag pattern has to accept Hangul syllables too, not just ASCII
# alphanumerics. Never contains '#' itself, so once a detection is split on
# the first '#' the remainder up to the first run of non-tag characters is
# the tag.
_RIOT_TAG_PATTERN = re.compile(r"[A-Za-z0-9가-힣]{2,6}")

# Tesseract (the engine this pipeline currently uses - see
# TesseractOCRExtractor) very often detects one Hangul SYLLABLE per box
# instead of a whole name as a single box, because its layout analysis
# mistakes each syllable block's small kerning gap for a word boundary
# (verified directly against a real participant-roster screenshot: a 3-4
# syllable nickname/game name routinely comes back as 3-4 separate
# single-character detections a few pixels apart). Every heuristic below
# that reconstructs a name/Riot ID (_best_name_match, _split_riot_id)
# assumes one detection per name, so adjacent same-row Hangul-only
# detections with a tight gap are re-joined in _merge_split_hangul() before
# anything else sees them. Scoped to Hangul-only text on both sides so it
# never touches a Riot ID tag/English text, which Tesseract already keeps
# intact as one box.
_HANGUL_SYLLABLE_START, _HANGUL_SYLLABLE_END = 0xAC00, 0xD7A3
MERGE_GAP_HEIGHT_RATIO = 0.6

Detection = tuple[list[list[float]], str, float]


def _center(bbox: list[list[float]]) -> tuple[float, float]:
    xs = [p[0] for p in bbox]
    ys = [p[1] for p in bbox]
    return sum(xs) / len(xs), sum(ys) / len(ys)


def _is_pure_hangul(text: str) -> bool:
    return bool(text) and all(_HANGUL_SYLLABLE_START <= ord(ch) <= _HANGUL_SYLLABLE_END for ch in text)


def _merge_split_hangul(row: list[tuple[float, float, float, float, str]]) -> list[tuple[float, str]]:
    """`row`, sorted left-to-right, is (center_x, left, right, height, text)
    per detection. Merges a run of adjacent pure-Hangul detections into one
    token (no separator - a Hangul name is never legitimately split by a
    real space at the syllable level) whenever the gap between them is
    small relative to their height; a real column boundary's gap is many
    times larger (see MERGE_GAP_HEIGHT_RATIO)."""
    merged: list[tuple[float, str]] = []
    group_cxs: list[float] = []
    group_texts: list[str] = []
    prev_right: Optional[float] = None
    prev_height: Optional[float] = None

    def _flush() -> None:
        if group_texts:
            merged.append((sum(group_cxs) / len(group_cxs), "".join(group_texts)))

    for cx, left, right, height, text in row:
        can_merge = (
            group_texts
            and _is_pure_hangul(group_texts[-1])
            and _is_pure_hangul(text)
            and prev_right is not None
            and prev_height is not None
            and (left - prev_right) <= prev_height * MERGE_GAP_HEIGHT_RATIO
        )
        if can_merge:
            group_texts.append(text)
            group_cxs.append(cx)
        else:
            _flush()
            group_texts, group_cxs = [text], [cx]
        prev_right, prev_height = right, height
    _flush()
    return merged


def cluster_rows(detections: list[Detection], image_height: float) -> list[list[tuple[float, str]]]:
    """Groups OCR detections into rows by y-proximity, sorting each row's
    contents left-to-right by x and re-joining Hangul text Tesseract split
    across multiple boxes (see _merge_split_hangul). Returns list of rows,
    each a list of (center_x, text)."""
    rows = _group_rows(detections, y_tolerance=image_height * ROW_Y_TOLERANCE_RATIO)
    return [_merge_split_hangul(row) for row in rows]


# (center_x, left, right, height, text) of one detection box.
_Box = tuple[float, float, float, float, str]


def _box_height(bbox: list[list[float]]) -> float:
    ys = [p[1] for p in bbox]
    return max(ys) - min(ys)


def _group_rows(detections: list[Detection], y_tolerance: float) -> list[list[_Box]]:
    """Groups detections into rows by y-proximity, each row sorted left to
    right."""

    def _edges(bbox: list[list[float]]) -> tuple[float, float, float]:
        xs = [p[0] for p in bbox]
        return min(xs), max(xs), _box_height(bbox)

    items = sorted(
        ((*_center(bbox), *_edges(bbox), text) for bbox, text, _conf in detections),
        key=lambda t: t[1],
    )

    rows: list[list[_Box]] = []
    current_row: list[_Box] = []
    row_y: Optional[float] = None

    for cx, cy, left, right, height, text in items:
        if row_y is None or abs(cy - row_y) <= y_tolerance:
            current_row.append((cx, left, right, height, text))
            row_y = cy if row_y is None else (row_y + cy) / 2
        else:
            rows.append(sorted(current_row, key=lambda t: t[0]))
            current_row = [(cx, left, right, height, text)]
            row_y = cy
    if current_row:
        rows.append(sorted(current_row, key=lambda t: t[0]))
    return rows


def _row_text(row: list[tuple[float, str]]) -> str:
    return " ".join(text for _, text in row)


def _extract_gold(text: str, kda_match: re.Match) -> int:
    """Gold is comma-grouped (e.g. "21,141"); KDA numbers never are, so
    searching the text with the KDA substring removed avoids the (rare)
    case where a KDA number could otherwise be mistaken for it."""
    without_kda = text[: kda_match.start()] + text[kda_match.end() :]
    match = _GOLD_PATTERN.search(without_kda)
    return int(match.group(0).replace(",", "")) if match else 0


def _best_name_match(row: list[tuple[float, str]], known_nicknames: list[str]) -> Optional[str]:
    """Fuzzy-matches OCR detections against registered player nicknames.
    Tries each detection's own text first (a name like "채 은" is usually
    one detection and its internal space must NOT be split), then adjacent
    pairs joined together (in case OCR did split one name across two boxes,
    e.g. champion icon separating level from name)."""
    texts = [text for _, text in row]
    candidates = list(texts) + [f"{texts[i]} {texts[i + 1]}" for i in range(len(texts) - 1)]
    for candidate in candidates:
        matches = get_close_matches(candidate, known_nicknames, n=1, cutoff=0.6)
        if matches:
            return matches[0]
    return None


def parse_rows_into_players(
    rows: list[list[tuple[float, str]]], known_nicknames: list[str]
) -> list[OCRPlayerRow]:
    """Row -> OCRPlayerRow. Team boundary is anchored on the literal "1번
    팀" / "2번 팀" header rows (falling back to a positional 5-then-5 split
    only if those headers weren't detected at all). Reliably extracts K/D/A
    and gold (both have unmistakable formats); CS/vision/damage come from a
    separate detail screenshot via extract_detail_stats()."""
    player_rows: list[OCRPlayerRow] = []
    current_team = 0
    saw_team_header = False

    for row in rows:
        text = _row_text(row)

        header_match = _TEAM_HEADER_PATTERN.search(text)
        if header_match:
            current_team = int(header_match.group(1)) - 1
            saw_team_header = True
            continue

        kda_match = _KDA_PATTERN.search(text)
        if not kda_match:
            continue

        team_index = (
            current_team if saw_team_header else (0 if len(player_rows) < PLAYERS_PER_TEAM else 1)
        )
        player_rows.append(
            OCRPlayerRow(
                raw_name=_best_name_match(row, known_nicknames) or text,
                team_index=team_index,
                kills=int(kda_match.group(1)),
                deaths=int(kda_match.group(2)),
                assists=int(kda_match.group(3)),
                gold=_extract_gold(text, kda_match),
            )
        )
    return player_rows


def _split_riot_id(text: str) -> Optional[tuple[Optional[str], str]]:
    """(game_name, tag_line) if `text` contains a '#'-delimited Riot ID,
    else None. `game_name` is None (not empty string) when the '#' sat at
    the very start of this box's text - OCR sometimes detects the game
    name and the "#TAG" suffix as two separate boxes when there's a visible
    gap before the '#', and the caller falls back to the previous box's
    text in that case. Only ever called on ONE detection box's own text,
    never a whole row's concatenated text, so a non-None `game_name` is
    exactly what OCR put on that one box, never contaminated by a
    neighboring box's content."""
    if "#" not in text:
        return None
    game_name, _, remainder = text.partition("#")
    tag_match = _RIOT_TAG_PATTERN.match(remainder.strip())
    if not tag_match:
        return None
    game_name = game_name.strip() or None
    return game_name, tag_match.group(0)


# A gap wider than this many text-heights between two boxes on a row is a
# column boundary (spreadsheet cell / table column), not a word break.
CELL_GAP_HEIGHT_RATIO = 1.0
# Inside one cell, a gap wider than this is a real space ("Hasta La Vista");
# anything tighter is OCR splitting one word ("플루오" + "린", "#" + "0217").
WORD_SPACE_HEIGHT_RATIO = 0.25
# A '#'-less cell counts as the Riot ID column if it starts this close to
# where the rows that do have a '#' start.
RIOT_COLUMN_TOLERANCE_HEIGHT_RATIO = 2.0


# A tier column ("다이아 4", "마스터 100", "언랭") that OCR glued onto a long
# Riot ID touching it - including Vision's usual misreads of the tier
# names (에메 -> 어머/에머, 플레 -> 플러). Requires the trailing number (or
# the standalone 언랭) so a game name merely containing "골드" survives.
_SPILLED_TIER_PATTERN = re.compile(
    r"\s*(?:(?:아이언|브론즈|실버|골드|플레|플래|플러|에메|에머|어머|다이아|마스터|그랜드마스터|그마|챌린저)\s*\d+|언랭).*$"
)


@dataclass
class _Cell:
    left: float
    right: float
    text: str


def _row_cells(row: list[_Box], text_height: float) -> list[_Cell]:
    cells: list[_Cell] = []
    for _cx, left, right, _height, text in row:
        text = text.strip()
        if not text:
            continue
        if cells and left - cells[-1].right <= text_height * CELL_GAP_HEIGHT_RATIO:
            gap = left - cells[-1].right
            joiner = " " if gap > text_height * WORD_SPACE_HEIGHT_RATIO else ""
            cells[-1] = _Cell(cells[-1].left, right, cells[-1].text + joiner + text)
        else:
            cells.append(_Cell(left, right, text))
    return cells


def _split_riot_cell(text: str) -> tuple[str, str]:
    """(game_name, tag_line) from one Riot ID cell. Spaces around the '#'
    are OCR word splits, not part of either half. Without a '#' (OCR
    missed it, e.g. "건전지 KR1"), the last word is taken as the tag when it
    looks like one; otherwise the tag is left empty for the operator to
    fill in on the review table."""
    spilled = _SPILLED_TIER_PATTERN.search(text)
    if spilled and spilled.start() > 0:
        text = text[: spilled.start()]
    if "#" in text:
        game_name, _, remainder = text.partition("#")
        tag_match = _RIOT_TAG_PATTERN.match(remainder.replace(" ", ""))
        return game_name.strip(), tag_match.group(0) if tag_match else ""
    words = text.split()
    if len(words) >= 2 and _RIOT_TAG_PATTERN.fullmatch(words[-1]):
        return " ".join(words[:-1]), words[-1]
    return text.strip(), ""


def parse_detections_into_riot_ids(detections: list[Detection]) -> list[OCRRiotIdRow]:
    """Detections -> OCRRiotIdRow, for a participant-roster screenshot
    (nickname + Riot ID per row, possibly with more columns such as tier
    and positions - e.g. a spreadsheet capture).

    Works on cells rather than single OCR boxes: Google Vision splits a
    Riot ID like "플루토리#0217" into several word boxes ("플루오", "린",
    "#", "0217"), so looking for one box containing the whole ID dropped
    most rows. Boxes are joined into cells by horizontal gap, the Riot ID
    column is located from the cells that contain a '#', and the nickname
    is the first cell left of it - every other column (tier, positions,
    ...) is ignored. Rows where OCR missed the '#' are still kept when a
    cell lines up with the Riot ID column, so the operator can fix them on
    the review table instead of losing the row entirely."""
    if not detections:
        return []
    text_height = statistics.median(_box_height(bbox) for bbox, _text, _conf in detections) or 1.0
    rows = [_row_cells(row, text_height) for row in _group_rows(detections, y_tolerance=text_height * 0.5)]

    hash_lefts = [cell.left for cells in rows for cell in cells if "#" in cell.text]
    if not hash_lefts:
        return []
    riot_column_left = statistics.median(hash_lefts)
    column_tolerance = text_height * RIOT_COLUMN_TOLERANCE_HEIGHT_RATIO

    parsed: list[OCRRiotIdRow] = []
    for cells in rows:
        riot_cell = next((cell for cell in cells if "#" in cell.text), None)
        if riot_cell is None:
            aligned = [cell for cell in cells if abs(cell.left - riot_column_left) <= column_tolerance]
            # A lone aligned cell is more likely a header/caption than a
            # roster row with a missed '#'.
            if not aligned or len(cells) < 3:
                continue
            riot_cell = min(aligned, key=lambda cell: abs(cell.left - riot_column_left))

        game_name, tag_line = _split_riot_cell(riot_cell.text)
        if not game_name:
            continue
        name_cells = [cell for cell in cells if cell.right <= riot_cell.left]
        parsed.append(
            OCRRiotIdRow(
                nickname=name_cells[0].text if name_cells else game_name,
                game_name=game_name,
                tag_line=tag_line,
                raw_text=" | ".join(cell.text for cell in cells),
            )
        )
    return parsed


def detect_winning_team(rows: list[list[tuple[float, str]]]) -> Optional[int]:
    """Best-effort only: some screenshot layouts show a single game-level
    승리/패배 badge with no clear per-team association, in which case this
    correctly returns None and the UI must ask the user directly rather
    than guess. Layouts that print 승리/패배 inside each team's block are
    still handled."""
    for i, row in enumerate(rows):
        text = _row_text(row)
        if _TEAM_HEADER_PATTERN.search(text):
            continue
        team_index = 0 if i < PLAYERS_PER_TEAM else 1
        if "승리" in text or "victory" in text.lower():
            return team_index
        if "패배" in text or "defeat" in text.lower():
            return 1 - team_index
    return None


def _extract_labeled_row_numbers(rows: list[list[tuple[float, str]]], label: str) -> list[int]:
    label_compact = label.replace(" ", "")
    for row in rows:
        text = _row_text(row)
        if text.replace(" ", "").startswith(label_compact):
            numbers = re.findall(r"\d{1,3}(?:,\d{3})*", text)
            return [int(n.replace(",", "")) for n in numbers]
    return []


def extract_kda_order(rows: list[list[tuple[float, str]]]) -> list[tuple[int, int, int]]:
    """The detail screenshot has a KDA row spanning all 10 columns - it's
    the most reliable join key back to the main scoreboard, since column
    order in this screenshot is NOT guaranteed to match the scoreboard's
    row order (observed directly against a real screenshot: one team's
    column order matched, the other team's didn't)."""
    best_row: list[tuple[int, int, int]] = []
    for row in rows:
        text = _row_text(row)
        matches = _KDA_PATTERN.findall(text)
        if len(matches) > len(best_row):
            best_row = [(int(k), int(d), int(a)) for k, d, a in matches]
    return best_row


def extract_detail_stats(rows: list[list[tuple[float, str]]]) -> dict[str, list]:
    """Parses the wide stat-comparison screenshot (one column per player).
    Returns each stat as a left-to-right list PLUS "kda" - the same-order
    list of (kills, deaths, assists) tuples to use as the join key back to
    the main scoreboard's participants (do not assume position alone lines
    the two screenshots up)."""
    stats: dict[str, list] = {key: _extract_labeled_row_numbers(rows, label) for key, label in STAT_LABELS.items()}
    stats["kda"] = extract_kda_order(rows)
    return stats


def match_detail_stats_by_kda(
    participants: list[dict], detail_stats: dict[str, list]
) -> tuple[int, list[str]]:
    """Joins the detail (CS/vision/damage/gold) screenshot's columns back to
    the main scoreboard's participants by K/D/A - the detail screenshot has
    no names, and its column order isn't guaranteed to match the
    scoreboard's row order (observed directly: one team's order matched,
    the other team's didn't), so KDA is the most reliable join key
    available. It is not a true identifier though: two participants can
    genuinely share one (e.g. two 0/0/0 supports in a short game). Mutates
    each *unambiguously* matched participant dict in place with its stats.
    Returns (matched_count, ambiguous_names) - names sharing a KDA with at
    least one other participant are deliberately left unmatched rather than
    guessed, since silently assigning one player's stats to a different
    player who happens to share their KDA would be wrong data with no
    indication anything went wrong."""
    by_kda: dict[tuple[int, int, int], list[dict]] = {}
    for p in participants:
        by_kda.setdefault((p["kills"], p["deaths"], p["assists"]), []).append(p)
    ambiguous_names = [p["raw_name"] for group in by_kda.values() if len(group) > 1 for p in group]

    kda_order = detail_stats.get("kda", [])
    matched_count = 0
    for i, kda in enumerate(kda_order):
        candidates = by_kda.get(tuple(kda), [])
        if len(candidates) != 1:
            continue
        target = candidates[0]
        for stat_name in ("cs", "vision_score", "damage", "gold"):
            values = detail_stats.get(stat_name, [])
            if i < len(values):
                target[stat_name] = values[i]
        matched_count += 1
    return matched_count, ambiguous_names
