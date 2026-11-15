"""Manifest entries from different source roots must not clobber or prune each other."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hks.adapters.core import hks_workspace_ingest_session_memory
from hks.core.manifest import load_manifest
from hks.ingest.pipeline import ingest


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.mark.integration
def test_same_relpath_from_another_root_is_refused_not_overwritten(
    tmp_path: Path, tmp_ks_root: Path
) -> None:
    a = tmp_path / "a"
    b = tmp_path / "b"
    _write(a / "README.md", "# Alpha\n\nAlpha budget is 10.\n")
    _write(b / "README.md", "# Beta\n\nBeta budget is 20.\n")

    first = ingest(a)
    second = ingest(b)

    assert first.created == ["README.md"]
    assert second.created == [] and second.updated == []
    assert [(issue.path, issue.reason) for issue in second.failures] == [
        ("README.md", "relpath_conflict")
    ]
    raw = (tmp_ks_root / "raw_sources" / "README.md").read_text(encoding="utf-8")
    assert "Alpha budget" in raw
    entry = load_manifest(tmp_ks_root / "manifest.json").entries["README.md"]
    assert entry.source_path == (a / "README.md").resolve().as_posix()


@pytest.mark.integration
def test_prune_only_removes_entries_under_the_ingested_root(
    tmp_path: Path, tmp_ks_root: Path
) -> None:
    a = tmp_path / "a"
    b = tmp_path / "b"
    c = tmp_path / "c"
    _write(a / "alpha.md", "# Alpha\n\nAlpha owns Atlas.\n")
    gone = _write(a / "gone.md", "# Gone\n\nGone soon.\n")
    _write(b / "beta.md", "# Beta\n\nBeta owns Bolt.\n")
    _write(c / "gamma.md", "# Gamma\n\nGamma owns Comet.\n")
    ingest(a)
    ingest(b)

    unrelated = ingest(c, prune=True)
    assert unrelated.pruned == []

    gone.unlink()
    scoped = ingest(a, prune=True)
    assert scoped.pruned == ["gone.md"]

    entries = load_manifest(tmp_ks_root / "manifest.json").entries
    assert sorted(entries) == ["alpha.md", "beta.md", "gamma.md"]


@pytest.mark.integration
def test_legacy_entries_are_backfilled_and_never_blindly_pruned(
    tmp_path: Path, tmp_ks_root: Path
) -> None:
    docs = tmp_path / "docs"
    _write(docs / "keep.md", "# Keep\n\nKeep me.\n")
    other = tmp_path / "other"
    _write(other / "legacy.md", "# Legacy\n\nIngested before source_path existed.\n")
    ingest(docs)
    ingest(other)

    manifest_path = tmp_ks_root / "manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    for entry in payload["entries"].values():
        entry.pop("source_path", None)
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    summary = ingest(docs, prune=True)

    assert summary.pruned == []
    entries = load_manifest(manifest_path).entries
    assert entries["keep.md"].source_path == (docs / "keep.md").resolve().as_posix()
    assert entries["legacy.md"].source_path is None


@pytest.mark.integration
def test_session_memory_days_keep_distinct_entries_under_prune(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    export_root = tmp_path / "export"
    ks_base = tmp_path / "ks-base"
    workspace_id = "demo"
    for day in ("2026-11-14", "2026-11-15"):
        _write(
            export_root / workspace_id / "daily" / day / "summary.md",
            "---\nhks_type: session_daily\n"
            f"date: {day}\n"
            "source_domain: session_memory\n"
            "generator: session2memory\n"
            f"workspace_id: {workspace_id}\n"
            f"---\n# {day}\n\n- note for {day}\n",
        )
    monkeypatch.setenv("HKS_SESSION2MEMORY_EXPORT_ROOT", str(export_root))
    monkeypatch.setenv("HKS_KS_ROOT_BASE", str(ks_base))
    monkeypatch.setenv("HKS_WORKSPACE_REGISTRY", str(tmp_path / "workspaces.json"))

    hks_workspace_ingest_session_memory(workspace_id=workspace_id, path="daily/2026-11-14")
    hks_workspace_ingest_session_memory(
        workspace_id=workspace_id, path="daily/2026-11-15", prune=True
    )

    entries = load_manifest(ks_base / workspace_id / "manifest.json").entries
    assert sorted(entries) == [
        "daily/2026-11-14/summary.md",
        "daily/2026-11-15/summary.md",
    ]


@pytest.mark.integration
def test_watch_scan_does_not_report_other_roots_as_missing(
    tmp_path: Path, tmp_ks_root: Path
) -> None:
    from hks.core.paths import runtime_paths
    from hks.watch.scanner import scan_sources

    a = tmp_path / "a"
    b = tmp_path / "b"
    _write(a / "alpha.md", "# Alpha\n\nAlpha owns Atlas.\n")
    gone = _write(a / "gone.md", "# Gone\n\nGone soon.\n")
    _write(b / "beta.md", "# Beta\n\nBeta owns Bolt.\n")
    ingest(a)
    ingest(b)
    gone.unlink()

    sources, _issues, _counts = scan_sources(
        paths=runtime_paths(),
        manifest_entries=load_manifest(tmp_ks_root / "manifest.json").entries,
        source_roots=[a],
    )

    missing = sorted(source.relpath for source in sources if source.state == "missing")
    assert missing == ["gone.md"]


@pytest.mark.integration
def test_moved_source_root_takes_over_its_relpaths(tmp_path: Path, tmp_ks_root: Path) -> None:
    old = tmp_path / "old"
    new = tmp_path / "new"
    _write(old / "same.md", "# Same\n\nUnchanged body.\n")
    _write(old / "edit.md", "# Edit\n\nBefore the move.\n")
    ingest(old)

    old.rename(new)
    _write(new / "edit.md", "# Edit\n\nAfter the move.\n")
    moved = ingest(new)

    assert moved.failures == []
    assert moved.updated == ["edit.md"]
    entries = load_manifest(tmp_ks_root / "manifest.json").entries
    assert entries["same.md"].source_path == (new / "same.md").resolve().as_posix()
    assert entries["edit.md"].source_path == (new / "edit.md").resolve().as_posix()
