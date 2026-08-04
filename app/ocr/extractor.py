from __future__ import annotations

from abc import ABC, abstractmethod

from app.ocr.parser import (
    cluster_rows,
    detect_winning_team,
    extract_detail_stats,
    parse_rows_into_players,
    parse_rows_into_riot_ids,
)
from app.ocr.schemas import MatchResultData, OCRRiotIdRow


class OCRExtractor(ABC):
    """Interface for the result-screen-to-data pipeline. Kept isolated so
    swapping the OCR backend doesn't touch match_service."""

    @abstractmethod
    def extract(self, image_path: str, known_nicknames: list[str]) -> MatchResultData:
        """`known_nicknames` is the current participant roster, used to
        fuzzy-match OCR-read names back to real Player records."""

    @abstractmethod
    def extract_detail_stats(self, image_path: str) -> dict[str, list]:
        """Reads the optional wide stat-comparison screenshot (CS, vision
        score, damage, ...). It has no player names, and its column order
        is not guaranteed to match extract()'s row order - the returned
        "kda" list is the join key the caller should match participants on."""

    @abstractmethod
    def extract_riot_ids(self, image_path: str) -> list[OCRRiotIdRow]:
        """Reads a participant-roster screenshot (nickname + Riot ID per
        row) for bulk player registration - see player_page.py's "스크린샷
        으로 일괄 등록" tab. Unrelated to the match-scoreboard extract()."""


_NOT_AVAILABLE_MESSAGE = (
    "OCR is not available - install the 'tesseract-ocr' system package "
    "(see packages.txt) and 'pytesseract' (pip install -r requirements.txt) to enable it"
)


class NotImplementedOCRExtractor(OCRExtractor):
    def extract(self, image_path: str, known_nicknames: list[str]) -> MatchResultData:
        raise NotImplementedError(_NOT_AVAILABLE_MESSAGE)

    def extract_detail_stats(self, image_path: str) -> dict[str, list]:
        raise NotImplementedError(_NOT_AVAILABLE_MESSAGE)

    def extract_riot_ids(self, image_path: str) -> list[OCRRiotIdRow]:
        raise NotImplementedError(_NOT_AVAILABLE_MESSAGE)


class TesseractOCRExtractor(OCRExtractor):
    """Reads LoL end-game result screenshots with Tesseract (via
    pytesseract): the main scoreboard (name, K/D/A, gold) via extract(), and
    optionally the wide stat-comparison screen (CS, vision, damage) via
    extract_detail_stats().

    Chosen over EasyOCR specifically because EasyOCR pulls in PyTorch, whose
    memory footprint alone exceeds Streamlit Community Cloud's ~1GB per-app
    limit and gets the whole process OOM-killed on first use (observed
    directly in production - see git history). Tesseract is a plain C++
    binary with no ML framework dependency, at a fraction of the memory
    cost.

    Calibrated against a real Korean-client screenshot (see
    tests/test_ocr_parser.py), but screen resolution/scale/client language
    all affect layout, so treat its output as a first draft. The UI that
    calls this always shows the parsed table for human review/correction
    before anything is saved."""

    def __init__(self, languages: list[str] | None = None) -> None:
        import pytesseract  # light import, no ML framework - deferred to first use

        pytesseract.get_tesseract_version()  # raises if the system binary isn't installed
        self._lang = "+".join(languages or ["kor", "eng"])

    def _read_rows(self, image_path: str) -> tuple[list[list[tuple[float, str]]], str]:
        import pytesseract
        from PIL import Image

        with Image.open(image_path) as img:
            image_height = img.height
            data = pytesseract.image_to_data(img, lang=self._lang, output_type=pytesseract.Output.DICT)

        detections: list[tuple[list[list[float]], str, float]] = []
        for i, text in enumerate(data["text"]):
            text = text.strip()
            if not text:
                continue
            left, top = data["left"][i], data["top"][i]
            width, height = data["width"][i], data["height"][i]
            bbox = [
                [left, top],
                [left + width, top],
                [left + width, top + height],
                [left, top + height],
            ]
            detections.append((bbox, text, float(data["conf"][i])))

        raw_text = "\n".join(text for _, text, _ in detections)
        return cluster_rows(detections, image_height), raw_text

    def extract(self, image_path: str, known_nicknames: list[str]) -> MatchResultData:
        rows, raw_text = self._read_rows(image_path)
        participants = parse_rows_into_players(rows, known_nicknames)
        winning_team_index = detect_winning_team(rows)

        return MatchResultData(
            participants=participants,
            winning_team_index=winning_team_index,
            raw_text=raw_text,
        )

    def extract_detail_stats(self, image_path: str) -> dict[str, list]:
        rows, _raw_text = self._read_rows(image_path)
        return extract_detail_stats(rows)

    def extract_riot_ids(self, image_path: str) -> list[OCRRiotIdRow]:
        rows, _raw_text = self._read_rows(image_path)
        return parse_rows_into_riot_ids(rows)


def build_ocr_extractor() -> OCRExtractor:
    try:
        return TesseractOCRExtractor()
    except Exception:  # noqa: BLE001 - missing package, or system tesseract-ocr binary not installed
        return NotImplementedOCRExtractor()
