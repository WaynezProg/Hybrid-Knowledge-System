from __future__ import annotations

from pathlib import Path

from hks.core.manifest import ManifestEntry
from hks.core.paths import runtime_paths
from hks.ingest.fingerprint import ParserFlags, compute_parser_fingerprint
from hks.watch.scanner import scan_sources


def _entry(relpath: str, source: Path, sha: str) -> ManifestEntry:
    return ManifestEntry(
        relpath=relpath,
        sha256=sha,
        format="md",
        size_bytes=source.stat().st_size,
        ingested_at="2026-04-26T00:00:00+00:00",
        parser_fingerprint=compute_parser_fingerprint("md", ParserFlags()),
    )


def test_scanner_marks_stale_source(tmp_path, tmp_ks_root) -> None:
    root = tmp_path / "docs"
    root.mkdir()
    source = root / "a.md"
    source.write_text("new", encoding="utf-8")
    entry = _entry("a.md", source, "old-sha")

    sources, _, counts = scan_sources(
        paths=runtime_paths(tmp_ks_root),
        manifest_entries={"a.md": entry},
        source_roots=[root],
    )

    assert sources[0].state == "stale"
    assert counts["stale"] == 1
