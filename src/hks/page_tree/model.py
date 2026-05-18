"""PageTree and TreeNode data model with JSON serialization."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class TreeNode:
    node_id: str
    title: str
    level: int
    start_offset: int
    end_offset: int
    children: list[TreeNode]
    summary: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "title": self.title,
            "level": self.level,
            "start_offset": self.start_offset,
            "end_offset": self.end_offset,
            "summary": self.summary,
            "metadata": dict(self.metadata),
            "children": [child.to_dict() for child in self.children],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TreeNode:
        return cls(
            node_id=str(data["node_id"]),
            title=str(data["title"]),
            level=int(data["level"]),
            start_offset=int(data["start_offset"]),
            end_offset=int(data["end_offset"]),
            children=[cls.from_dict(child) for child in data.get("children", [])],
            summary=str(data.get("summary", "")),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass(frozen=True, slots=True)
class PageTree:
    source_relpath: str
    source_format: str
    doc_title: str
    root_nodes: list[TreeNode]
    build_method: str
    built_at: str
    total_nodes: int
    source_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_relpath": self.source_relpath,
            "source_format": self.source_format,
            "doc_title": self.doc_title,
            "root_nodes": [node.to_dict() for node in self.root_nodes],
            "build_method": self.build_method,
            "built_at": self.built_at,
            "total_nodes": self.total_nodes,
            "source_sha256": self.source_sha256,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PageTree:
        return cls(
            source_relpath=str(data["source_relpath"]),
            source_format=str(data["source_format"]),
            doc_title=str(data["doc_title"]),
            root_nodes=[TreeNode.from_dict(node) for node in data.get("root_nodes", [])],
            build_method=str(data["build_method"]),
            built_at=str(data["built_at"]),
            total_nodes=int(data["total_nodes"]),
            source_sha256=str(data["source_sha256"]),
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_json(cls, text: str) -> PageTree:
        return cls.from_dict(json.loads(text))

    def flat_nodes(self) -> list[TreeNode]:
        nodes: list[TreeNode] = []

        def walk(current_nodes: list[TreeNode]) -> None:
            for node in current_nodes:
                nodes.append(node)
                walk(node.children)

        walk(self.root_nodes)
        return nodes

    def find_node_for_offset(self, offset: int) -> TreeNode | None:
        def search(nodes: list[TreeNode]) -> TreeNode | None:
            for node in nodes:
                if node.start_offset <= offset < node.end_offset:
                    deeper = search(node.children)
                    return deeper if deeper is not None else node
            return None

        return search(self.root_nodes)

    def section_path(self, node_id: str) -> str | None:
        path: list[str] = []

        def find(nodes: list[TreeNode]) -> bool:
            for node in nodes:
                path.append(node.title)
                if node.node_id == node_id:
                    return True
                if find(node.children):
                    return True
                path.pop()
            return False

        if find(self.root_nodes):
            return " > ".join(path)
        return None
