"""JSON-backed graph store for Phase 2 entity/relation reasoning."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from slugify import slugify

from hks.core.manifest import atomic_write
from hks.core.paths import RuntimePaths, runtime_paths

type EntityType = Literal["Person", "Project", "Document", "Event", "Concept"]
type RelationType = Literal["owns", "depends_on", "impacts", "references", "belongs_to"]


@dataclass(slots=True)
class GraphNode:
    id: str
    type: EntityType
    label: str
    aliases: list[str] = field(default_factory=list)
    source_relpaths: list[str] = field(default_factory=list)
    wiki_slugs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "label": self.label,
            "aliases": sorted(set(self.aliases)),
            "source_relpaths": sorted(set(self.source_relpaths)),
            "wiki_slugs": sorted(set(self.wiki_slugs)),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> GraphNode:
        return cls(
            id=str(payload["id"]),
            type=payload["type"],
            label=str(payload["label"]),
            aliases=list(payload.get("aliases", [])),
            source_relpaths=list(payload.get("source_relpaths", [])),
            wiki_slugs=list(payload.get("wiki_slugs", [])),
        )


@dataclass(slots=True)
class GraphEdge:
    id: str
    relation: RelationType
    source: str
    target: str
    source_relpath: str
    evidence: str

    def to_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "relation": self.relation,
            "source": self.source,
            "target": self.target,
            "source_relpath": self.source_relpath,
            "evidence": self.evidence,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> GraphEdge:
        return cls(
            id=str(payload["id"]),
            relation=payload["relation"],
            source=str(payload["source"]),
            target=str(payload["target"]),
            source_relpath=str(payload["source_relpath"]),
            evidence=str(payload["evidence"]),
        )


@dataclass(slots=True)
class GraphDocumentArtifacts:
    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)


@dataclass(slots=True)
class GraphPayload:
    version: int = 1
    nodes: dict[str, GraphNode] = field(default_factory=dict)
    edges: dict[str, GraphEdge] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "nodes": {
                node_id: node.to_dict()
                for node_id, node in sorted(self.nodes.items(), key=lambda item: item[0])
            },
            "edges": {
                edge_id: edge.to_dict()
                for edge_id, edge in sorted(self.edges.items(), key=lambda item: item[0])
            },
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> GraphPayload:
        return cls(
            version=int(payload.get("version", 1)),
            nodes={
                node_id: GraphNode.from_dict(node_payload)
                for node_id, node_payload in dict(payload.get("nodes", {})).items()
            },
            edges={
                edge_id: GraphEdge.from_dict(edge_payload)
                for edge_id, edge_payload in dict(payload.get("edges", {})).items()
            },
        )


def make_node_id(entity_type: EntityType, label: str) -> str:
    base = slugify(label, separator="-").strip("-")
    if not base:
        digest = hashlib.sha1(label.encode("utf-8"), usedforsecurity=False).hexdigest()[:12]
        base = digest
    return f"{entity_type.lower()}:{base}"


def make_edge_id(
    *,
    relation: RelationType,
    source_id: str,
    target_id: str,
    source_relpath: str,
) -> str:
    payload = f"{source_relpath}|{relation}|{source_id}|{target_id}"
    digest = hashlib.sha1(payload.encode("utf-8"), usedforsecurity=False).hexdigest()[:16]
    return f"edge:{digest}"


class GraphStore:
    def __init__(self, paths: RuntimePaths | None = None) -> None:
        self.paths = paths or runtime_paths()

    @property
    def graph_path(self) -> Path:
        return self.paths.graph_file

    def ensure(self) -> None:
        self.paths.graph_dir.mkdir(parents=True, exist_ok=True)

    def load(self) -> GraphPayload:
        if not self.graph_path.exists():
            return GraphPayload()
        payload = json.loads(self.graph_path.read_text(encoding="utf-8"))
        return GraphPayload.from_dict(payload)

    def save(self, payload: GraphPayload) -> None:
        self.ensure()
        atomic_write(self.graph_path, json.dumps(payload.to_dict(), ensure_ascii=False, indent=2))

    def replace_document(self, relpath: str, artifacts: GraphDocumentArtifacts) -> GraphPayload:
        payload = self.load()
        self._remove_document_from_payload(payload, relpath)
        for node in artifacts.nodes:
            existing = payload.nodes.get(node.id)
            if existing is None:
                payload.nodes[node.id] = node
                continue
            payload.nodes[node.id] = self._merge_node(existing, node)
        for edge in artifacts.edges:
            payload.edges[edge.id] = edge
        self.save(payload)
        return payload

    def delete_document(self, relpath: str) -> None:
        payload = self.load()
        self._remove_document_from_payload(payload, relpath)
        self.save(payload)

    def count(self) -> tuple[int, int]:
        payload = self.load()
        return (len(payload.nodes), len(payload.edges))

    def _remove_document_from_payload(self, payload: GraphPayload, relpath: str) -> None:
        payload.edges = {
            edge_id: edge
            for edge_id, edge in payload.edges.items()
            if edge.source_relpath != relpath
        }
        for node_id, node in list(payload.nodes.items()):
            remaining_relpaths = sorted(path for path in node.source_relpaths if path != relpath)
            if not remaining_relpaths:
                payload.nodes.pop(node_id, None)
                continue
            payload.nodes[node_id] = GraphNode(
                id=node.id,
                type=node.type,
                label=node.label,
                aliases=node.aliases,
                source_relpaths=remaining_relpaths,
                wiki_slugs=node.wiki_slugs,
            )
        dangling_nodes = {
            node_id
            for node_id in payload.nodes
            if all(
                edge.source != node_id and edge.target != node_id for edge in payload.edges.values()
            )
            and payload.nodes[node_id].type != "Document"
        }
        for node_id in dangling_nodes:
            payload.nodes.pop(node_id, None)

    def _merge_node(self, existing: GraphNode, incoming: GraphNode) -> GraphNode:
        preferred_type = existing.type
        if preferred_type == "Concept" and incoming.type != "Concept":
            preferred_type = incoming.type
        preferred_label = existing.label
        if len(incoming.label) > len(existing.label):
            preferred_label = incoming.label
        return GraphNode(
            id=existing.id,
            type=preferred_type,
            label=preferred_label,
            aliases=sorted(set(existing.aliases) | set(incoming.aliases) | {preferred_label}),
            source_relpaths=sorted(set(existing.source_relpaths) | set(incoming.source_relpaths)),
            wiki_slugs=sorted(set(existing.wiki_slugs) | set(incoming.wiki_slugs)),
        )
