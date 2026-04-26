from __future__ import annotations

from hks.graphify.clustering import cluster
from hks.graphify.models import GraphifyEdge, GraphifyNode


def test_graphify_clustering_is_deterministic() -> None:
    nodes = [
        GraphifyNode(id="b", label="B", kind="concept", source_layer="graph", source_ref="b"),
        GraphifyNode(id="a", label="A", kind="concept", source_layer="graph", source_ref="a"),
    ]
    edges = [
        GraphifyEdge(
            id="edge:1",
            source="a",
            target="b",
            relation="references",
            evidence="EXTRACTED",
            confidence_score=1.0,
            weight=1.0,
            source_layer="graph",
            source_ref="edge:1",
        )
    ]

    first_nodes, first_communities = cluster(nodes, edges)
    second_nodes, second_communities = cluster(list(reversed(nodes)), edges)

    assert [node.to_dict() for node in first_nodes] == [node.to_dict() for node in second_nodes]
    assert [item.to_dict() for item in first_communities] == [
        item.to_dict() for item in second_communities
    ]
