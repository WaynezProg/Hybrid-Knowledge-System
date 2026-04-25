from __future__ import annotations

import pytest

from hks.core.manifest import DerivedArtifacts, ManifestEntry
from hks.graph.store import GraphEdge, GraphNode, GraphPayload
from hks.lint.checks import run_checks
from hks.lint.models import RuntimeSnapshot, WikiPageRecord
from hks.storage.wiki import WikiPage


def _entry(
    relpath: str,
    *,
    wiki_pages: list[str] | None = None,
    vector_ids: list[str] | None = None,
    graph_nodes: list[str] | None = None,
    graph_edges: list[str] | None = None,
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
