from __future__ import annotations

from pathlib import Path

import pytest

from hks.core.manifest import atomic_write, compute_sha256, resume_or_rebuild
from hks.core.paths import runtime_paths


@pytest.mark.unit
@pytest.mark.us1
def test_manifest_helpers_write_atomically_and_hash_consistently(tmp_path: Path) -> None:
    target = tmp_path / "manifest.json"
    atomic_write(target, '{"version": 1}')
    atomic_write(target, '{"version": 2}')

    assert target.read_text(encoding="utf-8") == '{"version": 2}'
    assert not (tmp_path / "manifest.json.tmp").exists()
    assert compute_sha256(target) == compute_sha256(target)


@pytest.mark.unit
@pytest.mark.us1
def test_resume_or_rebuild_reconstructs_manifest_from_raw_sources(tmp_path: Path) -> None:
    paths = runtime_paths(tmp_path / "ks")
    paths.raw_sources.mkdir(parents=True)
    source = paths.raw_sources / "project-atlas.md"
    source.write_text("# Atlas\n\nSummary", encoding="utf-8")

    manifest = resume_or_rebuild(paths)

    assert paths.manifest.exists()
    assert list(manifest.entries) == ["project-atlas.md"]
    entry = manifest.entries["project-atlas.md"]
    assert entry.relpath == "project-atlas.md"
    assert entry.format == "md"
    assert entry.size_bytes == source.stat().st_size
