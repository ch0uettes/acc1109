from __future__ import annotations

import re
from difflib import get_close_matches
from typing import Optional

from app.ocr.schemas import OCRPlayerRow, OCRRiotIdRow

# EasyOCR row grouping: LoL's end-game table lines are evenly spaced, so
# nearby detections are clustered into one row using a tolerance sized as a
# fraction of image height (not a fixed pixel count) so it holds up across
# different screenshot resolutions.
ROW_Y_TOLERANCE_RATIO = 0.015

PLAYERS_PER_TEAM = 5

_KDA_PATTERN = re.compile(r"(\d+)\s*/\s*(\d+)\s*/\s*(\d+)")
_GOLD_PATTERN = re.compile(r"\d{1,3}(?:,\d{3})+")
# The scoreboard splits teams with an explicit "1번 팀" / "2번 팀" label row
# (which also carries the *team's* aggregate KDA - easy to mistake for a
# player row, so it's matched and skipped explicitly before anything else).
_TEAM_HEADER_PATTERN = re.compile(r"\d+\s*번\s*팀")

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

# Riot ID tags are short alphanumeric region/custom codes (e.g. "KR1",
# "NA1", "1234") - never containing '#' themselves, so once a detection is
# split on the first '#' the remainder up to the first run of non-tag
# characters is the tag.
_RIOT_TAG_PATTERN = re.compile(r"[A-Za-z0-9]{2,6}")

Detection = tuple[list[list[float]], str, float]


def _center(bbox: list[list[float]]) -> tuple[float, float]:
    xs = [p[0] for p in bbox]
    ys = [p[1] for p in bbox]
    return sum(xs) / len(xs), sum(ys) / len(ys)


def cluster_rows(detections: list[Detection], image_height: float) -> list[list[tuple[float, str]]]:
    """Groups OCR detections into rows by y-proximity, sorting each row's
    contents left-to-right by x. Returns list of rows, each a list of
    (center_x, text)."""
    y_tolerance = image_height * ROW_Y_TOLERANCE_RATIO
    items = sorted(
        ((*_center(bbox), text) for bbox, text, _conf in detections),
        key=lambda t: t[1],
    )

    rows: list[list[tuple[float, str]]] = []
    current_row: list[tuple[float, str]] = []
    row_y: Optional[float] = None

    for cx, cy, text in items:
        if row_y is None or abs(cy - row_y) <= y_tolerance:
            current_row.append((cx, text))
            row_y = cy if row_y is None else (row_y + cy) / 2
        else:
            rows.append(sorted(current_row, key=lambda t: t[0]))
            current_row = [(cx, text)]
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

        if _TEAM_HEADER_PATTERN.search(text):
            current_team = 1 if saw_team_header else 0
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


def parse_rows_into_riot_ids(rows: list[list[tuple[float, str]]]) -> list[OCRRiotIdRow]:
    """Row -> OCRRiotIdRow, for a participant-roster screenshot (nickname +
    Riot ID per row) rather than a match scoreboard. Only rows containing a
    '#' are kept - anything else (headers, blank lines, unrelated text) is
    silently skipped, so this tolerates an arbitrary screenshot layout as
    long as nickname and Riot ID share one visual row.

    The Riot ID's own game_name is read from whichever single detection box
    actually contains the '#' - never guessed by splitting the row's full
    concatenated text, which would have no reliable boundary between an
    adjacent nickname and the game name. Every other box on the row is
    treated as nickname text; if none remain, the game_name itself doubles
    as the nickname guess (the common case where the operator's display
    name and Riot ID's game name are the same)."""
    riot_id_rows: list[OCRRiotIdRow] = []

    for row in rows:
        riot_id = None
        tag_box_index = None
        for i, (_, text) in enumerate(row):
            riot_id = _split_riot_id(text)
            if riot_id is not None:
                tag_box_index = i
                break
        if riot_id is None:
            continue

        game_name, tag_line = riot_id
        game_name_box_index = tag_box_index
        if game_name is None:
            # '#TAG' was its own box - the game name is whatever OCR put in
            # the box immediately before it, if any.
            if tag_box_index == 0:
                continue
            game_name = row[tag_box_index - 1][1].strip()
            if not game_name:
                continue
            game_name_box_index = tag_box_index - 1

        excluded = {tag_box_index, game_name_box_index}
        other_texts = [text for i, (_, text) in enumerate(row) if i not in excluded]
        nickname = " ".join(t.strip() for t in other_texts if t.strip()) or game_name

        riot_id_rows.append(
            OCRRiotIdRow(
                nickname=nickname,
                game_name=game_name,
                tag_line=tag_line,
                raw_text=_row_text(row),
            )
        )

    return riot_id_rows


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
