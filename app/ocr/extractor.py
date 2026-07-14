from __future__ import annotations

from abc import ABC, abstractmethod

from app.ocr.parser import cluster_rows, detect_winning_team, extract_detail_stats, parse_rows_into_players
from app.ocr.schemas import MatchResultData


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


class NotImplementedOCRExtractor(OCRExtractor):
    def extract(self, image_path: str, known_nicknames: list[str]) -> MatchResultData:
        raise NotImplementedError(
            "OCR is not available - install 'easyocr' (pip install -r requirements.txt) to enable it"
        )

    def extract_detail_stats(self, image_path: str) -> dict[str, list]:
        raise NotImplementedError(
            "OCR is not available - install 'easyocr' (pip install -r requirements.txt) to enable it"
        )


class EasyOCRExtractor(OCRExtractor):
    """Reads LoL end-game result screenshots with EasyOCR: the main
    scoreboard (name, K/D/A, gold) via extract(), and optionally the wide
    stat-comparison screen (CS, vision, damage) via extract_detail_stats().

    Calibrated against a real Korean-client screenshot (see
    tests/test_ocr_parser.py), but screen resolution/scale/client language
    all affect layout, so treat its output as a first draft. The UI that
    calls this always shows the parsed table for human review/correction
    before anything is saved."""

    def __init__(self, languages: list[str] | None = None) -> None:
        import easyocr  # heavy import (torch) - deferred to first use

        self._reader = easyocr.Reader(languages or ["ko", "en"], gpu=False)

    def _read_rows(self, image_path: str) -> tuple[list[list[tuple[float, str]]], str]:
        from PIL import Image

        with Image.open(image_path) as img:
            image_height = img.height

        detections = self._reader.readtext(image_path)
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


def build_ocr_extractor() -> OCRExtractor:
    try:
        import easyocr  # noqa: F401
    except ImportError:
        return NotImplementedOCRExtractor()
    return EasyOCRExtractor()
