"""OCR child process timeout must not depend on `with_timeout` (thread-safe)."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest
from PIL import Image

from hks.ingest import ocr
from hks.ingest.guards import with_timeout
from hks.ingest.ocr import OCRConfig, ocr_subprocess_timeout, run_ocr
from hks.ingest.parsers import image as image_parser

_CHILD_SLEEP_SEC = 8


def _slow_engine(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    binary = tmp_path / "fake-tesseract"
    # `exec` so killing the child leaves no orphan holding the output pipes.
    binary.write_text(f"#!/bin/sh\nexec sleep {_CHILD_SLEEP_SEC}\n", encoding="utf-8")
    binary.chmod(0o755)
    config = OCRConfig(binary=str(binary), version="fake", languages=("eng",))
    monkeypatch.setattr(ocr, "resolve_ocr_config", lambda: config)


def _run_in_thread(target) -> tuple[list[BaseException], float]:  # type: ignore[no-untyped-def]
    errors: list[BaseException] = []

    def _wrapper() -> None:
        try:
            target()
        except BaseException as exc:  # noqa: BLE001 - surfaced to the test
            errors.append(exc)

    started = time.monotonic()
    worker = threading.Thread(target=_wrapper)
    worker.start()
    worker.join(timeout=_CHILD_SLEEP_SEC + 5)
    assert not worker.is_alive()
    return errors, time.monotonic() - started


@pytest.mark.unit
def test_run_ocr_kills_slow_engine_on_worker_thread(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _slow_engine(tmp_path, monkeypatch)
    picture = Image.new("L", (8, 8), color=255)

    errors, elapsed = _run_in_thread(lambda: run_ocr(picture, timeout_seconds=1))

    assert len(errors) == 1 and isinstance(errors[0], TimeoutError)
    assert elapsed < 4, f"waited for the child instead of killing it ({elapsed:.1f}s)"


@pytest.mark.unit
def test_image_parse_times_out_near_limit_on_worker_thread(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Same shape as the pipeline: `with_timeout(limit)` around the image parser."""

    _slow_engine(tmp_path, monkeypatch)
    monkeypatch.setenv("HKS_IMAGE_TIMEOUT_SEC", "5")
    monkeypatch.setattr(ocr, "_OCR_TIMEOUT_MARGIN_SEC", 4.0)  # child budget ~1s
    source = tmp_path / "scan.png"
    Image.new("L", (8, 8), color=255).save(source)

    def _body() -> None:
        with with_timeout(5):
            image_parser.parse(source, "png")

    errors, elapsed = _run_in_thread(_body)

    assert len(errors) == 1 and isinstance(errors[0], TimeoutError)
    assert elapsed < 4, f"waited for the child instead of killing it ({elapsed:.1f}s)"


@pytest.mark.unit
def test_ocr_subprocess_timeout_stays_inside_budget() -> None:
    assert ocr_subprocess_timeout(30) == pytest.approx(29.5)
    assert ocr_subprocess_timeout(0) == pytest.approx(0.1)
