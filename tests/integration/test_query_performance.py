from __future__ import annotations

import math
import shutil
import time
from pathlib import Path

import pytest

from hks.cli import app


def _copy_to_count(source: Path, target: Path, *, total: int) -> Path:
    target.mkdir(parents=True, exist_ok=True)
    originals = sorted(path for path in source.iterdir() if path.is_file())
    created = 0
    for copy_index in range(math.ceil(total / len(originals))):
        for original in originals:
            destination = target / f"{original.stem}-{copy_index}{original.suffix}"
            shutil.copy2(original, destination)
            created += 1
            if created == total:
                return target
    return target


def _p95(samples: list[float]) -> float:
    ordered = sorted(samples)
    index = max(0, math.ceil(len(ordered) * 0.95) - 1)
    return ordered[index]


@pytest.mark.integration
def test_query_p95_stays_under_three_seconds(
    cli_runner,
    valid_fixtures: Path,
    tmp_path: Path,
) -> None:
    docs = _copy_to_count(valid_fixtures, tmp_path / "docs", total=50)
    ingest_result = cli_runner.invoke(app, ["ingest", str(docs)])
    assert ingest_result.exit_code == 0

    durations: list[float] = []
    for _ in range(50):
        start = time.perf_counter()
        result = cli_runner.invoke(app, ["query", "summary Atlas"])
        durations.append(time.perf_counter() - start)
        assert result.exit_code == 0

    p95 = _p95(durations)
    assert p95 < 3.0, f"query p95={p95:.3f}s >= 3.0s"
