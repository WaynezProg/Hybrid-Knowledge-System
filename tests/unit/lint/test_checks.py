from __future__ import annotations

import pytest

from hks.core.manifest import DerivedArtifacts, ManifestEntry
from hks.graph.store import GraphEdge, GraphNode, GraphPayload
from hks.lint.checks import run_checks
from hks.lint.models import RuntimeSnapshot, WikiPageRecord
from hks.page_tree.model import PageTree, TreeNode
from hks.storage.wiki import WikiPage


def _entry(
    relpath: str,
    *,
    wiki_pages: list[str] | None = None,
    vector_ids: list[str] | None = None,
    graph_nodes: list[str] | None = None,
    graph_edges: list[str] | None = None,
    page_tree: str | None = None,
    parser_fingerprint: str = "*",
) -> ManifestEntry:
    return ManifestEntry(
        relpath=relpath,
        sha256="0" * 64,
        format="txt",
        size_bytes=10,
        ingested_at="2026-04-26T00:00:00+00:00",
        parser_fingerprint=parser_fingerprint,
        derived=DerivedArtifacts(
            wiki_pages=wiki_pages or [],
            vector_ids=vector_ids or [],
            graph_nodes=graph_nodes or [],
            graph_edges=graph_edges or [],
            page_tree=page_tree,
        ),
    )


def _page(slug: str, source_relpath: str) -> WikiPageRecord:
    return WikiPageRecord(
        file_slug=slug,
        page=WikiPage(
            slug=slug,
            title=slug,
            summary=slug,
            body="body",
            source_relpath=source_relpath,
            origin="ingest",
            updated_at="2026-04-26T00:00:00+00:00",
        ),
    )


def _tree(relpath: str, *, end_offset: int = 4) -> PageTree:
    return PageTree(
        source_relpath=relpath,
        source_format="txt",
        doc_title=relpath,
        root_nodes=[
            TreeNode(
                node_id="n1",
                title="Root",
                level=1,
                start_offset=0,
                end_offset=end_offset,
                children=[],
            )
        ],
        build_method="rule",
        built_at="2026-05-19T00:00:00+00:00",
        total_nodes=1,
        source_sha256="0" * 64,
    )


@pytest.mark.unit
def test_run_checks_returns_no_findings_for_consistent_snapshot() -> None:
    snapshot = RuntimeSnapshot(
        manifest_entries={
            "doc.txt": _entry(
                "doc.txt",
                wiki_pages=["doc"],
                vector_ids=["doc:0"],
                graph_nodes=["document:doc"],
            )
        },
        raw_source_relpaths={"doc.txt"},
        wiki_pages={"doc": _page("doc", "doc.txt")},
        wiki_index_slugs=["doc"],
        vector_ids={"doc:0"},
        graph=GraphPayload(
            nodes={
                "document:doc": GraphNode(
                    id="document:doc",
                    type="Document",
                    label="doc",
                    source_relpaths=["doc.txt"],
                    wiki_slugs=["doc"],
                )
            }
        ),
    )

    assert run_checks(snapshot) == []


@pytest.mark.unit
def test_run_checks_reports_core_category_set() -> None:
    snapshot = RuntimeSnapshot(
        manifest_entries={
            "doc.txt": _entry(
                "doc.txt",
                wiki_pages=["missing-page"],
                vector_ids=["missing-vector"],
                graph_nodes=["missing-node"],
                graph_edges=["missing-edge"],
                parser_fingerprint="txt:v0:",
            )
        },
        raw_source_relpaths={"orphan.txt"},
        wiki_pages={
            "orphan": _page("orphan", "orphan.txt"),
            "bad-source": _page("bad-source", "missing-source.txt"),
            "dup-a": _page("dup", "doc.txt"),
            "dup-b": _page("dup", "doc.txt"),
        },
        wiki_index_slugs=["dead", "dead"],
        vector_ids={"orphan-vector"},
        graph=GraphPayload(
            nodes={
                "orphan-node": GraphNode(
                    id="orphan-node",
                    type="Concept",
                    label="orphan",
                    source_relpaths=["missing-source.txt"],
                )
            },
            edges={
                "dangling-edge": GraphEdge(
                    id="dangling-edge",
                    relation="references",
                    source="missing-a",
                    target="missing-b",
                    source_relpath="doc.txt",
                    evidence="broken",
                )
            },
        ),
    )

    categories = {finding.category for finding in run_checks(snapshot)}

    assert {
        "orphan_page",
        "dead_link",
        "duplicate_slug",
        "manifest_wiki_mismatch",
        "wiki_source_mismatch",
        "dangling_manifest_entry",
        "orphan_raw_source",
        "manifest_vector_mismatch",
        "orphan_vector_chunk",
        "graph_drift",
        "fingerprint_drift",
    } <= categories


@pytest.mark.unit
def test_run_checks_reports_tree_missing_and_orphan() -> None:
    snapshot = RuntimeSnapshot(
        manifest_entries={"doc.txt": _entry("doc.txt", page_tree="missing-tree")},
        raw_source_relpaths={"doc.txt"},
        wiki_pages={},
        wiki_index_slugs=[],
        vector_ids=set(),
        graph=GraphPayload(),
        page_tree_slugs={"orphan-tree"},
    )

    by_category = {finding.category: finding for finding in run_checks(snapshot)}

    assert by_category["tree_missing"].severity == "warning"
    assert by_category["tree_missing"].target == "missing-tree"
    assert by_category["tree_orphan"].severity == "warning"
    assert by_category["tree_orphan"].target == "orphan-tree"


@pytest.mark.unit
def test_run_checks_reports_tree_offset_mismatch_and_chunk_gap() -> None:
    snapshot = RuntimeSnapshot(
        manifest_entries={
            "doc.txt": _entry("doc.txt", vector_ids=["doc:0", "doc:1"], page_tree="doc")
        },
        raw_source_relpaths={"doc.txt"},
        wiki_pages={},
        wiki_index_slugs=[],
        vector_ids={"doc:0", "doc:1"},
        graph=GraphPayload(),
        page_tree_slugs={"doc"},
        page_trees={"doc": _tree("doc.txt", end_offset=50)},
        source_text_by_relpath={"doc.txt": "tiny"},
        vector_metadatas={
            "doc:0": {"source_relpath": "doc.txt", "chunk_idx": 0},
            "doc:1": {"source_relpath": "doc.txt", "chunk_idx": 1, "tree_node_id": "missing"},
        },
    )

    findings = run_checks(snapshot)
    by_category = {finding.category: finding for finding in findings}

    assert by_category["tree_offset_mismatch"].severity == "info"
    assert by_category["tree_offset_mismatch"].target == "doc:n1"
    gap_targets = {
        finding.target
        for finding in findings
        if finding.category == "tree_node_chunk_gap"
    }
    assert gap_targets == {"doc:0", "doc:1"}
