from __future__ import annotations

import json
import math
import shutil
import time
from pathlib import Path

import pytest

from hks.cli import app


def _expand_to_fifty_docs(source: Path, target: Path) -> Path:
    target.mkdir(parents=True, exist_ok=True)
    originals = sorted(path for path in source.iterdir() if path.is_file())
    copies_needed = math.ceil(50 / len(originals))
    created = 0
    for index in range(copies_needed):
        for original in originals:
            destination = target / f"{original.stem}-{index}{original.suffix}"
            shutil.copy2(original, destination)
            created += 1
            if created == 50:
                return target
    return target


@pytest.mark.integration
@pytest.mark.us1
def test_reingest_is_idempotent_and_faster(
    cli_runner,
    valid_fixtures: Path,
    tmp_path: Path,
    tmp_ks_root: Path,
) -> None:
    docs = _expand_to_fifty_docs(valid_fixtures, tmp_path / "docs")

    start = time.perf_counter()
    first = cli_runner.invoke(app, ["ingest", str(docs)])
    first_duration = time.perf_counter() - start

    start = time.perf_counter()
    second = cli_runner.invoke(app, ["ingest", str(docs)])
    second_duration = time.perf_counter() - start

    assert first.exit_code == 0
    assert second.exit_code == 0

    payload = json.loads(second.stdout)
    skipped = payload["trace"]["steps"][0]["detail"]["skipped"]
    assert len(skipped) == 50
    assert len(list((tmp_ks_root / "wiki" / "pages").glob("*.md"))) == 50
    assert second_duration <= first_duration * 0.5
