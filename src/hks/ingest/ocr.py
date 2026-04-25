"""Local OCR helpers for Phase 3 image ingest."""

from __future__ import annotations

import csv
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from hks.errors import ExitCode, KSError

_DEFAULT_LANGS = "eng+chi_tra"
_DEFAULT_PSM = 3
_PREPROCESS_SIGNATURE = "exif_transpose+grayscale+autocontrast"
_TESSERACT_HINT = "brew install tesseract tesseract-lang"
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


@dataclass(frozen=True, slots=True)
class OCRLine:
    text: str
    confidence: float
    bbox_left: int
    bbox_top: int
    bbox_width: int
    bbox_height: int
    source_engine: str


@dataclass(frozen=True, slots=True)
class OCRConfig:
    binary: str
    version: str
    languages: tuple[str, ...]
    psm: int = _DEFAULT_PSM

    @property
    def lang_spec(self) -> str:
        return "+".join(self.languages)

    @property
    def engine_label(self) -> str:
        return f"tesseract-{self.version}"


def preprocess_signature() -> str:
    return _PREPROCESS_SIGNATURE


def ocr_engine_signature() -> str:
    config = resolve_ocr_config()
    return f"{config.engine_label}+{config.lang_spec}"


@lru_cache(maxsize=1)
def resolve_ocr_config() -> OCRConfig:
    binary = shutil.which("tesseract")
    if binary is None:
        raise KSError(
            "缺少 OCR engine：找不到 tesseract",
            exit_code=ExitCode.GENERAL,
            code="OCR_ENGINE_UNAVAILABLE",
            hint=_TESSERACT_HINT,
        )

    version_output = subprocess.run(
        [binary, "--version"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.splitlines()
    first_line = version_output[0].strip() if version_output else "tesseract unknown"
    version = first_line.removeprefix("tesseract ").strip() or "unknown"

    available = set(_available_languages(binary))
    requested = _requested_languages()
    missing = [language for language in requested if language not in available]
    if missing:
        raise KSError(
            "缺少 OCR 語言包",
            exit_code=ExitCode.GENERAL,
            code="OCR_LANG_MISSING",
            details=[f"missing: {', '.join(missing)}"],
            hint="install `tesseract-lang` or override HKS_OCR_LANGS",
        )
    return OCRConfig(binary=binary, version=version, languages=requested)


def load_preprocessed_image(path: Path, *, max_pixels: int) -> Image.Image:
    try:
        with Image.open(path) as original:
            rotated = ImageOps.exif_transpose(original)
            pixel_count = rotated.width * rotated.height
            if pixel_count > max_pixels:
                raise KSError(
                    "影像像素總量超出上限",
                    exit_code=ExitCode.DATAERR,
                    code="OVERSIZED_DECODED",
                    details=[f"{path.name}: {pixel_count} pixels > {max_pixels}"],
                )
            grayscale = rotated.convert("L")
            processed = ImageOps.autocontrast(grayscale)
            processed.load()
            return processed
    except KSError:
        raise
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError) as exc:
        raise KSError(
            "影像解碼失敗",
            exit_code=ExitCode.DATAERR,
            code="CORRUPT",
            details=[f"{path.name}: {exc}"],
        ) from exc


def run_ocr(image: Image.Image) -> list[OCRLine]:
    config = resolve_ocr_config()
    with tempfile.TemporaryDirectory(prefix="hks_ocr_") as tmp_dir:
        tmp_root = Path(tmp_dir)
        input_path = tmp_root / "input.png"
        output_base = tmp_root / "ocr"
        image.save(input_path, format="PNG")
        subprocess.run(
            [
                config.binary,
                str(input_path),
                str(output_base),
                "-l",
                config.lang_spec,
                "--psm",
                str(config.psm),
                "tsv",
            ],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        return _parse_tsv(output_base.with_suffix(".tsv"), config.engine_label)


@lru_cache(maxsize=1)
def _available_languages(binary: str) -> tuple[str, ...]:
    output = subprocess.run(
        [binary, "--list-langs"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.splitlines()
    return tuple(line.strip() for line in output[1:] if line.strip())


def _requested_languages() -> tuple[str, ...]:
    raw = os.environ.get("HKS_OCR_LANGS", _DEFAULT_LANGS)
    parts: list[str] = []
    seen: set[str] = set()
    for chunk in raw.replace(",", "+").split("+"):
        language = chunk.strip()
        if not language or language in seen:
            continue
        seen.add(language)
        parts.append(language)
    return tuple(parts or ["eng"])


def _parse_tsv(path: Path, engine_label: str) -> list[OCRLine]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        grouped: dict[tuple[int, int, int], list[dict[str, str]]] = {}
        for row in reader:
            text = (row.get("text") or "").strip()
            if not text:
                continue
            conf = float(row.get("conf") or "-1")
            if conf < 0:
                continue
            key = (
                int(row.get("block_num") or "0"),
                int(row.get("par_num") or "0"),
                int(row.get("line_num") or "0"),
            )
            grouped.setdefault(key, []).append(row)

    collected: list[tuple[int, int, OCRLine]] = []
    for words in grouped.values():
        words.sort(key=lambda row: int(row.get("left") or "0"))
        text = _join_tokens([(row.get("text") or "").strip() for row in words])
        if not text:
            continue
        left = min(int(row.get("left") or "0") for row in words)
        top = min(int(row.get("top") or "0") for row in words)
        right = max(int(row.get("left") or "0") + int(row.get("width") or "0") for row in words)
        bottom = max(int(row.get("top") or "0") + int(row.get("height") or "0") for row in words)
        confidences = [float(row.get("conf") or "0") for row in words]
        line = OCRLine(
            text=text,
            confidence=round(sum(confidences) / len(confidences) / 100.0, 4),
            bbox_left=left,
            bbox_top=top,
            bbox_width=max(0, right - left),
            bbox_height=max(0, bottom - top),
            source_engine=engine_label,
        )
        collected.append((top, left, line))
    collected.sort(key=lambda item: (item[0], item[1]))
    return [line for _, _, line in collected]


def _join_tokens(tokens: list[str]) -> str:
    if not tokens:
        return ""
    joined = " ".join(token for token in tokens if token)
    joined = re.sub(r"\s+([,.:;!?%])", r"\1", joined)
    joined = re.sub(r"([([{])\s+", r"\1", joined)
    joined = re.sub(r"\s+([)\]}])", r"\1", joined)
    joined = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", joined)
    joined = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[:：])", "", joined)
    joined = re.sub(r"(?<=[:：])\s+(?=[\u4e00-\u9fff])", " ", joined)
    joined = re.sub(r"\s{2,}", " ", joined)
    if _CJK_RE.search(joined):
        joined = joined.replace(" ：", "：").replace(" : ", ": ")
    return joined.strip()
