from __future__ import annotations

import base64
import io

from PIL import Image

from app.ocr.extractor import GoogleVisionOCRExtractor


def _save_png(tmp_path, width: int, height: int) -> str:
    path = tmp_path / f"shot_{width}x{height}.png"
    Image.new("RGB", (width, height), "white").save(path)
    return str(path)


def _decoded_size(content: str) -> tuple[int, int]:
    with Image.open(io.BytesIO(base64.b64decode(content))) as img:
        return img.size


def test_small_screenshot_is_upscaled_2x_before_ocr(tmp_path):
    content, height = GoogleVisionOCRExtractor._encode_image(_save_png(tmp_path, 507, 711))

    assert _decoded_size(content) == (1014, 1422)
    assert height == 1422  # boxes come back in the upscaled image's coordinates


def test_full_resolution_screenshot_is_sent_unchanged(tmp_path):
    path = _save_png(tmp_path, 1920, 1080)

    content, height = GoogleVisionOCRExtractor._encode_image(path)

    with open(path, "rb") as f:
        assert base64.b64decode(content) == f.read()
    assert height == 1080
