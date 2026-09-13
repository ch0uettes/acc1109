"""Parses a CSV/TXT/XLSX participant-roster file into the same
(nickname, game_name, tag_line) shape the screenshot-OCR bulk registration
tab produces (app.ocr.schemas.OCRRiotIdRow), so both paths feed the exact
same review-and-edit table in player_page.py's "스크린샷으로 일괄 등록" tab
before anything is registered - a structured file is just a more reliable
input than OCR when the operator already has one (e.g. a Discord export or
a hand-compiled roster), not a different registration flow.
"""
from __future__ import annotations

import io
from pathlib import Path

import pandas as pd

from app.ocr.parser import _split_riot_id
from app.ocr.schemas import OCRRiotIdRow

SUPPORTED_EXTENSIONS = (".csv", ".txt", ".xlsx", ".xls")

# "닉네임" is deliberately NOT in the unambiguous set below - this app's
# own real users have used it to label the *Riot ID* column (game#tag),
# the opposite of what the English word suggests (see
# _find_combined_riot_id_column's content-based fallback, which is what
# actually resolves that case). It stays safe to match here only because
# this alias set is used when an explicit game_name+tag_line pair already
# exists, i.e. no '#'-column ambiguity is possible in that branch.
_NICKNAME_ALIASES = {"nickname", "name", "닉네임", "이름"}
_UNAMBIGUOUS_NICKNAME_ALIASES = {"nickname", "name", "이름"}
_GAME_NAME_ALIASES = {"game_name", "gamename", "게임이름", "게임 이름", "게임명"}
_TAG_LINE_ALIASES = {"tag_line", "tagline", "tag", "태그"}
_RIOT_ID_ALIASES = {"riot_id", "riotid", "riot id", "라이엇아이디", "라이엇 아이디", "라이엇id"}

# A candidate "riot id" column must look like one (contain '#') in at
# least this fraction of its non-empty values before content-detection
# trusts it - guards against picking an unrelated column (e.g. a free-text
# "비고" note) that just happens to contain a stray '#'.
_RIOT_ID_CONTENT_RATIO_THRESHOLD = 0.5


class UnsupportedRosterFileError(ValueError):
    """Raised for a file extension this importer doesn't handle, or a file
    whose columns can't be resolved into nickname/game_name/tag_line at
    all - the caller is expected to show this message directly to the
    operator, same "OCR gives a first draft, human reviews" contract as
    the screenshot path, just failing earlier when there's nothing to
    review yet."""


def parse_roster_file(data: bytes, filename: str) -> list[OCRRiotIdRow]:
    ext = Path(filename).suffix.lower()
    if ext in (".xlsx", ".xls"):
        df = pd.read_excel(io.BytesIO(data), dtype=str).fillna("")
        return [] if df.empty else _rows_from_dataframe(df)
    if ext == ".csv":
        df = pd.read_csv(io.BytesIO(data), dtype=str).fillna("")
        return [] if df.empty else _rows_from_dataframe(df)
    if ext == ".txt":
        return _parse_txt(_decode_text(data))
    raise UnsupportedRosterFileError(f"지원하지 않는 파일 형식입니다: {filename}")


def _decode_text(data: bytes) -> str:
    for encoding in ("utf-8-sig", "cp949"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _parse_txt(text: str) -> list[OCRRiotIdRow]:
    """A plain-text roster has no fixed shape the way a real CSV/XLSX does,
    so it gets two strategies rather than relying on delimiter-sniffing
    alone (which real user files have shown to be unreliable - see the
    module's test suite for the exact case: a header line delimited by
    "/" ("이름/닉네임") followed by data lines delimited by a plain space
    ("허재혁 플루오린#0217"), which confused pandas' sniffer into putting
    every data row into a single column and leaving the second column
    entirely empty).

    If comma or tab shows up in most lines, it's treated as a real
    delimited table (so an explicit nickname/game_name/tag_line-style
    header still works, same as CSV). Otherwise each non-blank line is
    parsed as its own whitespace-separated "닉네임 게임이름#태그" entry -
    the token containing '#' is the Riot ID, every other token on that
    line is the nickname. A line with no '#' token at all (a header row,
    a stray blank, anything unparseable) is silently skipped rather than
    guessed - the same "ambiguous/unmatched -> skip" rule the OCR path
    already follows for exactly this reason."""
    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    if not lines:
        return []

    delimiter = _detect_line_delimiter(lines)
    if delimiter is not None:
        df = pd.read_csv(io.StringIO("\n".join(lines)), sep=delimiter, dtype=str).fillna("")
        return [] if df.empty else _rows_from_dataframe(df)

    rows: list[OCRRiotIdRow] = []
    for line in lines:
        tokens = line.split()
        tag_token_index = next((i for i, t in enumerate(tokens) if "#" in t), None)
        if tag_token_index is None:
            continue
        split = _split_riot_id(tokens[tag_token_index])
        if split is None:
            continue
        game_name, tag_line = split
        game_name = game_name or tokens[tag_token_index].split("#", 1)[0].strip()
        nickname = " ".join(tokens[:tag_token_index] + tokens[tag_token_index + 1 :]).strip() or game_name
        rows.append(OCRRiotIdRow(nickname=nickname, game_name=game_name, tag_line=tag_line, raw_text=line))
    return rows


def _detect_line_delimiter(lines: list[str]) -> str | None:
    for delimiter in (",", "\t"):
        ratio = sum(1 for line in lines if delimiter in line) / len(lines)
        if ratio >= 0.5:
            return delimiter
    return None


def _normalize(column: object) -> str:
    return str(column).strip().lower()


def _rows_from_dataframe(df: pd.DataFrame) -> list[OCRRiotIdRow]:
    by_normalized_name = {_normalize(c): c for c in df.columns}

    def _find(aliases: set[str]) -> object | None:
        return next((by_normalized_name[a] for a in aliases if a in by_normalized_name), None)

    game_name_col = _find(_GAME_NAME_ALIASES)
    tag_line_col = _find(_TAG_LINE_ALIASES)

    if game_name_col is not None and tag_line_col is not None:
        nickname_col = _find(_NICKNAME_ALIASES)
        return [
            OCRRiotIdRow(
                nickname=_cell(row, nickname_col) or _cell(row, game_name_col),
                game_name=_cell(row, game_name_col),
                tag_line=_cell(row, tag_line_col),
                raw_text=_raw_text(row),
            )
            for _, row in df.iterrows()
            if _cell(row, game_name_col) and _cell(row, tag_line_col)
        ]

    riot_id_col = _find(_RIOT_ID_ALIASES) or _find_combined_riot_id_column(df)
    if riot_id_col is None:
        raise UnsupportedRosterFileError(
            "'게임이름#태그' 형식의 라이엇 아이디 열을 찾지 못했습니다. "
            "컬럼 이름을 nickname/game_name/tag_line(또는 닉네임/게임이름/태그)로 맞추거나, "
            "'게임이름#태그' 형식의 값이 담긴 열이 있는지 확인해주세요."
        )

    nickname_col = _find(_UNAMBIGUOUS_NICKNAME_ALIASES)
    if nickname_col == riot_id_col:
        # The same column can't be both - e.g. a header name that matches
        # a nickname alias but whose values are actually the combined Riot
        # ID (content-detection already claimed it above). Treat this as
        # "no separate nickname column" rather than using the raw,
        # un-split "game#tag" text as the nickname.
        nickname_col = None
    if nickname_col is None:
        remaining = [c for c in df.columns if c != riot_id_col]
        nickname_col = remaining[0] if remaining else None

    rows: list[OCRRiotIdRow] = []
    for _, row in df.iterrows():
        raw_id = _cell(row, riot_id_col)
        split = _split_riot_id(raw_id)
        if split is None:
            continue
        game_name, tag_line = split
        game_name = game_name or raw_id.split("#", 1)[0].strip()
        nickname = (_cell(row, nickname_col) if nickname_col is not None else "") or game_name
        rows.append(OCRRiotIdRow(nickname=nickname, game_name=game_name, tag_line=tag_line, raw_text=_raw_text(row)))
    return rows


def _find_combined_riot_id_column(df: pd.DataFrame) -> object | None:
    """No column is explicitly named as a Riot ID - find whichever column
    actually holds '#'-formatted values by content instead of guessing
    from a header name that real spreadsheets have used inconsistently."""
    best_col, best_ratio = None, 0.0
    for col in df.columns:
        values = df[col].astype(str)
        non_empty = values[values.str.strip() != ""]
        if non_empty.empty:
            continue
        ratio = non_empty.str.contains("#").mean()
        if ratio > best_ratio:
            best_col, best_ratio = col, ratio
    return best_col if best_ratio >= _RIOT_ID_CONTENT_RATIO_THRESHOLD else None


def _cell(row: pd.Series, col: object | None) -> str:
    if col is None:
        return ""
    return str(row[col]).strip()


def _raw_text(row: pd.Series) -> str:
    return " ".join(str(v).strip() for v in row.values if str(v).strip())
