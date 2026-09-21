from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, File, UploadFile

from app.ocr.extractor import build_ocr_extractor
from app.ocr.schemas import MatchResultData, OCRRiotIdRow

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
