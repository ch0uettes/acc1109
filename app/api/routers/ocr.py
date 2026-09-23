from __future__ import annotations

import json
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, UploadFile
from pydantic import BaseModel

from app.ocr.extractor import build_ocr_extractor
from app.ocr.parser import match_detail_stats_by_kda
from app.ocr.schemas import MatchResultData, OCRPlayerRow, OCRRiotIdRow

router = APIRouter(prefix="/ocr", tags=["ocr"])


def _save_upload(file: UploadFile, contents: bytes) -> str:
    suffix = Path(file.filename or "upload.png").suffix
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(contents)
        return tmp.name


@router.post("/match-result", response_model=MatchResultData)
async def extract_match_result(file: UploadFile = File(...), known_nicknames: str = "") -> MatchResultData:
    nicknames = [n for n in known_nicknames.split(",") if n]
    tmp_path = _save_upload(file, await file.read())
    return build_ocr_extractor().extract(tmp_path, nicknames)


@router.post("/detail-stats", response_model=dict)
async def extract_detail_stats(file: UploadFile = File(...)) -> dict:
    tmp_path = _save_upload(file, await file.read())
    return build_ocr_extractor().extract_detail_stats(tmp_path)


@router.post("/riot-ids", response_model=list[OCRRiotIdRow])
async def extract_riot_ids(file: UploadFile = File(...)) -> list[OCRRiotIdRow]:
    tmp_path = _save_upload(file, await file.read())
    return build_ocr_extractor().extract_riot_ids(tmp_path)


class MergeDetailStatsResponse(BaseModel):
    participants: list[OCRPlayerRow]
    matched_count: int
    ambiguous_names: list[str]


@router.post("/detail-stats/merge", response_model=MergeDetailStatsResponse)
async def merge_detail_stats(
    file: UploadFile = File(...), participants: str = Form(...)
) -> MergeDetailStatsResponse:
    """Reads the wide stat-comparison screenshot and joins it into an
    already-parsed main scoreboard (from /ocr/match-result) by KDA - same
    two-step flow match_page.py used, just split across two HTTP calls
    since the client (not a Streamlit session) holds the in-between state.
    `participants` is the JSON-encoded list[OCRPlayerRow] from that
    earlier call."""
    tmp_path = _save_upload(file, await file.read())
    detail_stats = build_ocr_extractor().extract_detail_stats(tmp_path)

    rows = [OCRPlayerRow(**p) for p in json.loads(participants)]
    dict_rows = [row.model_dump() for row in rows]
    matched_count, ambiguous_names = match_detail_stats_by_kda(dict_rows, detail_stats)

    return MergeDetailStatsResponse(
        participants=[OCRPlayerRow(**d) for d in dict_rows],
        matched_count=matched_count,
        ambiguous_names=ambiguous_names,
    )
