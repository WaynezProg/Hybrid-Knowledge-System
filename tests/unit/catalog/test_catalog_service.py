from __future__ import annotations

from hks.catalog.service import list_sources
from hks.core.manifest import DerivedArtifacts, Manifest, ManifestEntry, save_manifest


def test_catalog_service_sorts_and_filters_sources(tmp_path) -> None:
    ks_root = tmp_path / "ks"
    (ks_root / "raw_sources").mkdir(parents=True)
    (ks_root / "raw_sources" / "a.md").write_text("A project", encoding="utf-8")
    (ks_root / "raw_sources" / "b.txt").write_text("B project", encoding="utf-8")
    save_manifest(
        Manifest(
            entries={
                "b.txt": ManifestEntry(
                    relpath="b.txt",
                    sha256="b" * 64,
                    format="txt",
                    size_bytes=9,
                    ingested_at="2026-04-26T00:00:00+00:00",
                    derived=DerivedArtifacts(vector_ids=["b:0"]),
                ),
                "a.md": ManifestEntry(
                    relpath="a.md",
                    sha256="a" * 64,
                    format="md",
                    size_bytes=9,
                    ingested_at="2026-04-26T00:00:00+00:00",
                    derived=DerivedArtifacts(vector_ids=["a:0"]),
                ),
            }
        ),
        ks_root / "manifest.json",
    )

    detail = list_sources(ks_root=ks_root, format="md")

    assert detail.total_count == 2
    assert detail.filtered_count == 1
    assert detail.sources is not None
    assert [entry.relpath for entry in detail.sources] == ["a.md"]
