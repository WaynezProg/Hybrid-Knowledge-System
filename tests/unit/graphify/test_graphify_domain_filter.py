"""Tests for Graphify domain-only filtering (include_artifacts=False)."""

from __future__ import annotations

from hks.graphify.builder import _filter_domain_only
from hks.graphify.models import GraphifyEdge, GraphifyNode, GraphifyProvenance


def _make_node(
    id: str,
    kind: str = "entity",
    label: str = "Test",
) -> GraphifyNode:
    return GraphifyNode(
        id=id,
        label=label,
        kind=kind,  # type: ignore[arg-type]
        source_layer="graph",
        source_ref=id,
        provenance=GraphifyProvenance(),
    )


def _make_edge(source: str, target: str, relation: str = "references") -> GraphifyEdge:
    return GraphifyEdge(
        id=f"edge:{source}-{target}",
        source=source,
        target=target,
        relation=relation,
        evidence="EXTRACTED",
        confidence_score=1.0,
        weight=1.0,
        source_layer="graph",
        source_ref="test",
    )


def test_excludes_source_and_wiki_page_nodes() -> None:
    """source and wiki_page kind nodes must be excluded from domain-only output."""
    nodes = [
        _make_node("source:readme-txt", kind="source", label="readme.txt"),
        _make_node("wiki:readme", kind="wiki_page", label="README"),
        _make_node("graph:person-alice", kind="entity", label="Alice"),
        _make_node("graph:concept-api", kind="entity", label="API Design"),
    ]
    edges = [
        _make_edge("wiki:readme", "source:readme-txt"),
        _make_edge("graph:person-alice", "graph:concept-api", "owns"),
    ]
    filtered_nodes, filtered_edges = _filter_domain_only(nodes, edges, set())

    node_ids = {n.id for n in filtered_nodes}
    assert node_ids == {"graph:person-alice", "graph:concept-api"}
    assert len(filtered_edges) == 1
    assert filtered_edges[0].source == "graph:person-alice"


def test_excludes_document_type_entity_nodes() -> None:
    """Entity nodes with type=Document in the graph are excluded from domain-only output."""
    nodes = [
        _make_node("graph:document-readme", kind="entity", label="README"),
        _make_node("graph:person-bob", kind="entity", label="Bob"),
        _make_node("graph:project-hks", kind="entity", label="HKS"),
    ]
    document_entity_ids = {"graph:document-readme"}
    edges = [
        _make_edge("graph:document-readme", "graph:person-bob", "references"),
        _make_edge("graph:person-bob", "graph:project-hks", "owns"),
    ]
    filtered_nodes, filtered_edges = _filter_domain_only(nodes, edges, document_entity_ids)

    node_ids = {n.id for n in filtered_nodes}
    assert node_ids == {"graph:person-bob", "graph:project-hks"}
    assert len(filtered_edges) == 1
    assert filtered_edges[0].relation == "owns"


def test_removes_dangling_edges_after_filtering() -> None:
    """Edges whose source or target was removed must also be removed."""
    nodes = [
        _make_node("source:data-csv", kind="source", label="data.csv"),
        _make_node("graph:concept-ml", kind="entity", label="ML"),
        _make_node("graph:person-carol", kind="entity", label="Carol"),
    ]
    edges = [
        _make_edge("graph:concept-ml", "source:data-csv", "references"),
        _make_edge("graph:concept-ml", "graph:person-carol", "impacts"),
    ]
    filtered_nodes, filtered_edges = _filter_domain_only(nodes, edges, set())

    node_ids = {n.id for n in filtered_nodes}
    assert "source:data-csv" not in node_ids
    # Edge pointing to removed source node must be gone
    assert len(filtered_edges) == 1
    assert filtered_edges[0].relation == "impacts"


def test_empty_result_when_only_artifacts() -> None:
    """When all nodes are artifacts, filtering produces empty lists."""
    nodes = [
        _make_node("source:a", kind="source"),
        _make_node("wiki:b", kind="wiki_page"),
    ]
    edges = [_make_edge("wiki:b", "source:a")]
    filtered_nodes, filtered_edges = _filter_domain_only(nodes, edges, set())

    assert filtered_nodes == []
    assert filtered_edges == []


def test_community_nodes_preserved() -> None:
    """Community-kind nodes should survive domain filtering."""
    nodes = [
        _make_node("graph:person-dave", kind="entity", label="Dave"),
        _make_node("community:c1", kind="community", label="Group 1"),
        _make_node("source:notes-md", kind="source", label="notes.md"),
    ]
    edges: list[GraphifyEdge] = []
    filtered_nodes, _ = _filter_domain_only(nodes, edges, set())

    node_ids = {n.id for n in filtered_nodes}
    assert "graph:person-dave" in node_ids
    assert "community:c1" in node_ids
    assert "source:notes-md" not in node_ids
