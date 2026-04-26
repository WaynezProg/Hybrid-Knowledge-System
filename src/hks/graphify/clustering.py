"""Deterministic community clustering for graphify output."""

from __future__ import annotations

from collections import defaultdict, deque

from hks.graphify.models import GraphifyCommunity, GraphifyEdge, GraphifyNode, GraphifyProvenance


def cluster(
    nodes: list[GraphifyNode],
    edges: list[GraphifyEdge],
) -> tuple[list[GraphifyNode], list[GraphifyCommunity]]:
    by_id = {node.id: node for node in nodes}
    adjacency: dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        if edge.source in by_id and edge.target in by_id:
            adjacency[edge.source].add(edge.target)
            adjacency[edge.target].add(edge.source)

    communities: list[GraphifyCommunity] = []
    node_to_community: dict[str, str] = {}
    seen: set[str] = set()
    for node_id in sorted(by_id):
        if node_id in seen:
            continue
        component: list[str] = []
        queue: deque[str] = deque([node_id])
        seen.add(node_id)
        while queue:
            current = queue.popleft()
            component.append(current)
            for neighbor in sorted(adjacency[current]):
                if neighbor not in seen:
                    seen.add(neighbor)
                    queue.append(neighbor)
        community_id = f"community:{len(communities) + 1:03d}"
        for member in component:
            node_to_community[member] = community_id
        representative_edges = [
            edge.id
            for edge in edges
            if edge.source in component and edge.target in component
        ][:10]
        label = _community_label([by_id[item] for item in component])
        communities.append(
            GraphifyCommunity(
                community_id=community_id,
                label=label,
                summary=f"{label} contains {len(component)} graphify nodes.",
                node_ids=sorted(component),
                representative_edge_ids=representative_edges,
                classification_method="deterministic",
                confidence_score=1.0,
                provenance=GraphifyProvenance(),
            )
        )

    clustered_nodes = [
        node.with_community(node_to_community.get(node.id, "community:000")) for node in nodes
    ]
    return sorted(clustered_nodes, key=lambda item: item.id), communities


def _community_label(nodes: list[GraphifyNode]) -> str:
    wiki_nodes = [node for node in nodes if node.kind == "wiki_page"]
    if wiki_nodes:
        return wiki_nodes[0].label
    entity_nodes = [node for node in nodes if node.kind == "entity"]
    if entity_nodes:
        return entity_nodes[0].label
    return nodes[0].label if nodes else "Graphify Community"
