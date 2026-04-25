from __future__ import annotations

import shutil
import time
from pathlib import Path

import pytest

from hks.cli import app


@pytest.mark.integration
def test_lint_medium_corpus_wall_clock(cli_runner, tmp_path: Path, valid_fixtures: Path) -> None:
    docs = tmp_path / "medium-docs"
    docs.mkdir()
    base_files = [path for path in valid_fixtures.iterdir() if path.is_file()]
    image_files = sorted((valid_fixtures / "image").iterdir())
    for index in range(50):
        source = base_files[index % len(base_files)]
        shutil.copy2(source, docs / f"{index:02d}-{source.name}")
    image_target = docs / "image"
    image_target.mkdir()
    for index in range(10):
        source = image_files[index % len(image_files)]
        shutil.copy2(source, image_target / f"{index:02d}-{source.name}")

    ingest_result = cli_runner.invoke(app, ["ingest", str(docs)])
    assert ingest_result.exit_code == 0, ingest_result.stdout

    started = time.perf_counter()
    lint_result = cli_runner.invoke(app, ["lint"])
    elapsed = time.perf_counter() - started

    assert lint_result.exit_code == 0, lint_result.stdout
    assert elapsed < 5.0
