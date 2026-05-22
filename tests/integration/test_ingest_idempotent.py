from __future__ import annotations

import json
import math
import shutil
import time
from pathlib import Path

import pytest

from hks.cli import app
from hks.core.manifest import load_manifest
from hks.core.paths import runtime_paths
from hks.storage.vector import VectorStore


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


@pytest.mark.integration
def test_legacy_manifest_reindexes_when_current_vector_collection_is_empty(
    cli_runner,
    monkeypatch: pytest.MonkeyPatch,
    working_docs: Path,
    tmp_ks_root: Path,
) -> None:
    first = cli_runner.invoke(app, ["ingest", str(working_docs)])
    assert first.exit_code == 0

    paths = runtime_paths(tmp_ks_root)
    manifest = load_manifest(paths.manifest)
    entry = manifest.entries["project-atlas.txt"]
    assert entry.derived.vector_ids

    # Simulate a pre-vector-versioning manifest after the store starts using a
    # different backend-specific collection.
    payload = json.loads(paths.manifest.read_text(encoding="utf-8"))
    derived = payload["entries"]["project-atlas.txt"]["derived"]
    for key in (
        "embedding_fingerprint",
        "vector_collection",
        "embedding_model",
        "embedding_dimension",
    ):
        derived.pop(key, None)
    paths.manifest.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(
        "hks.storage.vector.collection_name_for_backend",
        lambda _backend: "hks_v1__simple__128_migrated",
    )

    second = cli_runner.invoke(app, ["ingest", str(working_docs)])

    assert second.exit_code == 0
    payload = json.loads(second.stdout)
    detail = payload["trace"]["steps"][0]["detail"]
    assert "project-atlas.txt" in detail["updated"]
    assert not detail["skipped"]
    assert VectorStore(paths).count() > 0

    reloaded = load_manifest(paths.manifest).entries["project-atlas.txt"]
    assert reloaded.derived.embedding_fingerprint is not None
    assert reloaded.derived.vector_collection == VectorStore(paths).collection_name
