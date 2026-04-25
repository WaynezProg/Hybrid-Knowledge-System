from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

import pytest

from hks.cli import app
from hks.ingest import pipeline as ingest_pipeline


def _copy_tree_contents(source: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for child in sorted(source.iterdir()):
        destination = target / child.name
        if child.is_dir():
            shutil.copytree(child, destination)
        else:
            shutil.copy2(child, destination)


@pytest.mark.integration
@pytest.mark.us3
def test_image_ingest_handles_degradation_cases(
    cli_runner,
    tmp_path: Path,
    fixtures_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    docs = tmp_path / "images"
    _copy_tree_contents(fixtures_root / "valid" / "image", docs)
    _copy_tree_contents(fixtures_root / "broken" / "image", docs)

    original_png_parser = ingest_pipeline._IMAGE_PARSERS["png"]

    def slow_timeout_parser(path: Path, source_format: str):
        if path.name == "timeout.png":
            time.sleep(6.0)
        return original_png_parser(path, source_format)

    monkeypatch.setitem(ingest_pipeline._IMAGE_PARSERS, "png", slow_timeout_parser)
    monkeypatch.setenv("HKS_IMAGE_TIMEOUT_SEC", "5")
    monkeypatch.setenv("HKS_IMAGE_MAX_FILE_MB", "1")

    result = cli_runner.invoke(app, ["ingest", str(docs)])

    assert result.exit_code == 65, result.stdout
    payload = json.loads(result.stdout)
    detail = payload["trace"]["steps"][0]["detail"]
    assert {"path": "corrupt.png", "reason": "corrupt"} in detail["failures"]
    assert {"path": "oversized.jpg", "reason": "oversized"} in detail["failures"]
    assert {"path": "timeout.png", "reason": "timeout"} in detail["failures"]
    assert {"path": "empty.jpg", "reason": "empty_file"} in detail["skipped"]
    assert {"path": "no-text.png", "reason": "ocr_empty"} in detail["skipped"]
    assert "atlas-dependency.png" in detail["created"]
