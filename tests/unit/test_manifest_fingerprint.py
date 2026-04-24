"""Unit tests for ManifestEntry.parser_fingerprint + compatibility rules."""

from __future__ import annotations

import json

import pytest

from hks.core.manifest import (
    DerivedArtifacts,
    Manifest,
    ManifestEntry,
    load_manifest,
    save_manifest,
)
from hks.ingest.fingerprint import (
    ParserFlags,
    are_fingerprints_compatible,
    compute_parser_fingerprint,
)


@pytest.mark.unit
def test_legacy_entry_loads_with_wildcard_fingerprint(tmp_path) -> None:
    legacy = {
        "version": 1,
        "entries": {
            "a.txt": {
                "relpath": "a.txt",
                "sha256": "deadbeef",
                "format": "txt",
                "size_bytes": 3,
                "ingested_at": "2026-01-01T00:00:00+00:00",
                "derived": {"wiki_pages": ["a"], "vector_ids": []},
            }
        },
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(legacy), encoding="utf-8")
    manifest = load_manifest(path)
    assert manifest.entries["a.txt"].parser_fingerprint == "*"


@pytest.mark.unit
def test_wildcard_matches_any_current_fingerprint() -> None:
    current_fp = compute_parser_fingerprint("docx", ParserFlags())
    assert are_fingerprints_compatible("*", current_fp)
    assert are_fingerprints_compatible("*", "pptx:v999:notes_exclude")


@pytest.mark.unit
def test_specific_fingerprint_only_matches_itself() -> None:
    current_fp = compute_parser_fingerprint("docx", ParserFlags())
    assert are_fingerprints_compatible(current_fp, current_fp)
    assert not are_fingerprints_compatible(current_fp, "docx:v0.0.0:")


@pytest.mark.unit
def test_pptx_notes_flag_changes_fingerprint() -> None:
    included = compute_parser_fingerprint("pptx", ParserFlags(pptx_notes=True))
    excluded = compute_parser_fingerprint("pptx", ParserFlags(pptx_notes=False))
    assert included != excluded
    assert excluded.endswith(":notes_exclude")


@pytest.mark.unit
def test_save_and_roundtrip_preserves_fingerprint(tmp_path) -> None:
    manifest = Manifest()
    manifest.entries["deck.pptx"] = ManifestEntry(
        relpath="deck.pptx",
        sha256="cafebabe",
        format="pptx",
        size_bytes=1024,
        ingested_at="2026-05-01T00:00:00+00:00",
        derived=DerivedArtifacts(wiki_pages=["deck"], vector_ids=["v1"]),
        parser_fingerprint="pptx:v1.0.2:notes_exclude",
    )
    path = tmp_path / "manifest.json"
    save_manifest(manifest, path)
    reloaded = load_manifest(path)
    assert reloaded.entries["deck.pptx"].parser_fingerprint == "pptx:v1.0.2:notes_exclude"
