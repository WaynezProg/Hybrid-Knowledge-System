from __future__ import annotations

from pathlib import Path
from typing import Any

import chromadb
import pytest

from hks.core.manifest import load_manifest
from hks.core.paths import runtime_paths
from hks.graph.store import GraphStore
from hks.ingest.pipeline import ingest
from hks.page_tree.store import TreeStore
from hks.storage.vector import COLLECTION_NAME


@pytest.mark.integration
def test_md_ingest_creates_page_tree_manifest_and_vector_metadata(
    tmp_path: Path,
    tmp_ks_root: Path,
) -> None:
    source = tmp_path / "project-guide.md"
    source.write_text(
        "# Project Guide\n\n"
        "Overview content for the guide.\n\n"
        "## Scope\n\n"
        + "Scope detail. " * 80
        + "\n\n## Risks\n\n"
        + "Risk detail. " * 80,
        encoding="utf-8",
    )

    summary = ingest(source)

    assert summary.created == ["project-guide.md"]
    paths = runtime_paths(tmp_ks_root)
    manifest = load_manifest(paths.manifest)
    entry = manifest.entries["project-guide.md"]
    assert entry.derived.page_tree is not None

    store = TreeStore(paths)
    tree = store.load(entry.derived.page_tree)
    assert tree.source_relpath == "project-guide.md"
    assert tree.source_format == "md"
    assert tree.doc_title == "Project Guide"
    assert tree.build_method == "rule"
    assert tree.source_sha256 == entry.sha256
    assert tree.total_nodes == 3
    assert len(tree.root_nodes) == 1
    assert [child.title for child in tree.root_nodes[0].children] == ["Scope", "Risks"]

    client = chromadb.PersistentClient(path=str(paths.vector_db))
    collection = client.get_collection(COLLECTION_NAME)
    metadatas = collection.get(ids=entry.derived.vector_ids, include=["metadatas"])["metadatas"]
    assert metadatas is not None
    assert any(
        metadata.get("tree_node_id") and metadata.get("tree_node_title")
        for metadata in metadatas
        if metadata is not None
    )


@pytest.mark.integration
def test_txt_ingest_creates_degenerate_page_tree(
    tmp_path: Path,
    tmp_ks_root: Path,
) -> None:
    source = tmp_path / "plain-notes.txt"
    source.write_text("Plain text without structural headings.", encoding="utf-8")

    summary = ingest(source)

    assert summary.created == ["plain-notes.txt"]
    paths = runtime_paths(tmp_ks_root)
    entry = load_manifest(paths.manifest).entries["plain-notes.txt"]
    assert entry.derived.page_tree is not None
    tree = TreeStore(paths).load(entry.derived.page_tree)
    assert tree.source_format == "txt"
    assert tree.total_nodes == 1
    assert tree.root_nodes[0].node_id == "n1"
    assert tree.root_nodes[0].title == "plain notes"


@pytest.mark.integration
def test_reingest_empty_source_removes_stale_page_tree(
    tmp_path: Path,
    tmp_ks_root: Path,
) -> None:
    source = tmp_path / "turn-empty.md"
    source.write_text("# Before\n\nContent.", encoding="utf-8")
    ingest(source)
    paths = runtime_paths(tmp_ks_root)
    first_entry = load_manifest(paths.manifest).entries["turn-empty.md"]
    assert first_entry.derived.page_tree is not None
    stale_tree_path = paths.page_trees / f"{first_entry.derived.page_tree}.json"
    assert stale_tree_path.exists()

    source.write_text("   \n\t\n", encoding="utf-8")
    summary = ingest(source)

    assert [issue.path for issue in summary.skipped] == ["turn-empty.md"]
    assert not stale_tree_path.exists()
    assert "turn-empty.md" not in load_manifest(paths.manifest).entries


@pytest.mark.integration
def test_prune_removes_stale_page_tree(
    tmp_path: Path,
    tmp_ks_root: Path,
) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    source = docs / "remove-me.md"
    source.write_text("# Remove Me\n\nContent.", encoding="utf-8")
    ingest(docs)
    paths = runtime_paths(tmp_ks_root)
    entry = load_manifest(paths.manifest).entries["remove-me.md"]
    assert entry.derived.page_tree is not None
    stale_tree_path = paths.page_trees / f"{entry.derived.page_tree}.json"
    assert stale_tree_path.exists()

    source.unlink()
    summary = ingest(docs, prune=True)

    assert summary.pruned == ["remove-me.md"]
    assert not stale_tree_path.exists()
    assert "remove-me.md" not in load_manifest(paths.manifest).entries


@pytest.mark.integration
def test_rollback_after_tree_save_removes_new_page_tree_and_manifest_entry(
    tmp_path: Path,
    tmp_ks_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "rollback.md"
    source.write_text("# Rollback\n\nContent.", encoding="utf-8")

    def fail_replace_document(self: GraphStore, relpath: str, artifacts: Any) -> None:
        raise RuntimeError("forced graph failure")

    monkeypatch.setattr(GraphStore, "replace_document", fail_replace_document)

    with pytest.raises(RuntimeError, match="forced graph failure"):
        ingest(source)

    paths = runtime_paths(tmp_ks_root)
    assert not (paths.page_trees / "rollback.json").exists()
    if paths.manifest.exists():
        assert "rollback.md" not in load_manifest(paths.manifest).entries
