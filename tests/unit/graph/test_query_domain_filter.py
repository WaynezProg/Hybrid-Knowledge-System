"""Tests that graph query excludes Document-type nodes."""
from __future__ import annotations

from hks.graph.query import answer_query
from hks.graph.store import GraphEdge, GraphNode, GraphPayload, GraphStore


def _payload_with_document_and_domain() -> GraphPayload:
    """Payload where a Document node participates in a 'causes' edge.

    Without domain filtering, the Document edge could appear in results
    because it shares the same relation type as the domain edge.
    """
    return GraphPayload(
        nodes={
            "document:readme": GraphNode(
                id="document:readme",
                type="Document",
                label="README",
                aliases=["README"],
                source_relpaths=["readme.md"],
            ),
            "concept:api-latency": GraphNode(
                id="concept:api-latency",
                type="Concept",
                label="API latency",
                aliases=["API latency"],
                source_relpaths=["readme.md"],
            ),
            "event:deployment-delay": GraphNode(
                id="event:deployment-delay",
                type="Event",
                label="deployment delay",
                aliases=["deployment delay"],
                source_relpaths=["readme.md"],
            ),
        },
        edges={
            "edge:doc-ref": GraphEdge(
                id="edge:doc-ref",
                relation="causes",
                source="document:readme",
                target="concept:api-latency",
                source_relpath="readme.md",
                evidence="README causes API latency awareness",
            ),
            "edge:domain": GraphEdge(
                id="edge:domain",
                relation="causes",
                source="concept:api-latency",
                target="event:deployment-delay",
                source_relpath="readme.md",
                evidence="API latency causes deployment delay",
            ),
        },
    )


class FakeGraphStore:
    def __init__(self, payload: GraphPayload) -> None:
        self._payload = payload

    def load(self) -> GraphPayload:
        return self._payload


def test_query_excludes_document_nodes():
    payload = _payload_with_document_and_domain()
    store = FakeGraphStore(payload)
    result = answer_query("API latency 導致什麼", graph_store=store)
    assert result is not None
    assert all(not nid.startswith("document:") for nid in result.node_ids)


def test_query_excludes_document_edges():
    payload = _payload_with_document_and_domain()
    store = FakeGraphStore(payload)
    result = answer_query("API latency 導致什麼", graph_store=store)
    assert result is not None
    assert "edge:doc-ref" not in result.edge_ids


def test_query_still_returns_domain_results():
    payload = _payload_with_document_and_domain()
    store = FakeGraphStore(payload)
    result = answer_query("API latency 導致什麼", graph_store=store)
    assert result is not None
    assert "edge:domain" in result.edge_ids
    assert result.relpaths == ["readme.md"]
