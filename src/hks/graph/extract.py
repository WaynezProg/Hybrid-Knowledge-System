"""Heuristic entity/relation extraction for Phase 2 graph updates."""

from __future__ import annotations

import re

from hks.graph.store import (
    EntityType,
    GraphDocumentArtifacts,
    GraphEdge,
    GraphNode,
    RelationType,
    make_edge_id,
    make_node_id,
)

_RELATION_PATTERNS: tuple[tuple[RelationType, str], ...] = (
    ("impacts", r"(?P<left>.+?)(?:會|將|直接)?影響(?P<right>.+)"),
    ("impacts", r"(?P<left>.+?)\s+affects?\s+(?P<right>.+)"),
    ("depends_on", r"(?P<left>.+?)依賴(?P<right>.+)"),
    ("depends_on", r"(?P<left>.+?)\s+depends on\s+(?P<right>.+)"),
    ("references", r"(?P<left>.+?)(?:引用|參考)(?P<right>.+)"),
    ("references", r"(?P<left>.+?)\s+references\s+(?P<right>.+)"),
    ("belongs_to", r"(?P<left>.+?)(?:屬於|隸屬於)(?P<right>.+)"),
    ("belongs_to", r"(?P<left>.+?)\s+belongs to\s+(?P<right>.+)"),
    ("owns", r"(?P<left>.+?)(?:擁有|負責)(?P<right>.+)"),
    ("owns", r"(?P<left>.+?)\s+owns\s+(?P<right>.+)"),
)


def extract_document_graph(
    *,
    relpath: str,
    title: str,
    body: str,
    wiki_slug: str,
) -> GraphDocumentArtifacts:
    nodes: dict[str, GraphNode] = {}
    edges: dict[str, GraphEdge] = {}
    document_node = _register_node(
        nodes,
        label=title,
        entity_type="Document",
        relpath=relpath,
        wiki_slug=wiki_slug,
    )

    for sentence in _sentence_candidates(body):
        for relation, pattern in _RELATION_PATTERNS:
            match = re.search(pattern, sentence, flags=re.IGNORECASE)
            if match is None:
                continue
            source_label = _clean_label(match.group("left"))
            if not source_label:
                continue
            source_node = _register_node(
                nodes,
                label=source_label,
                entity_type=_infer_entity_type(source_label, default="Concept"),
                relpath=relpath,
            )
            edges.setdefault(
                make_edge_id(
                    relation="references",
                    source_id=document_node.id,
                    target_id=source_node.id,
                    source_relpath=relpath,
                ),
                GraphEdge(
                    id=make_edge_id(
                        relation="references",
                        source_id=document_node.id,
                        target_id=source_node.id,
                        source_relpath=relpath,
                    ),
                    relation="references",
                    source=document_node.id,
                    target=source_node.id,
                    source_relpath=relpath,
                    evidence=sentence,
                ),
            )
            for target_label in _split_targets(match.group("right")):
                target = _clean_label(target_label)
                if not target:
                    continue
                target_node = _register_node(
                    nodes,
                    label=target,
                    entity_type=_infer_entity_type(target, default="Concept"),
                    relpath=relpath,
                )
                edge_id = make_edge_id(
                    relation=relation,
                    source_id=source_node.id,
                    target_id=target_node.id,
                    source_relpath=relpath,
                )
                edges[edge_id] = GraphEdge(
                    id=edge_id,
                    relation=relation,
                    source=source_node.id,
                    target=target_node.id,
                    source_relpath=relpath,
                    evidence=sentence,
                )
                doc_edge_id = make_edge_id(
                    relation="references",
                    source_id=document_node.id,
                    target_id=target_node.id,
                    source_relpath=relpath,
                )
                edges.setdefault(
                    doc_edge_id,
                    GraphEdge(
                        id=doc_edge_id,
                        relation="references",
                        source=document_node.id,
                        target=target_node.id,
                        source_relpath=relpath,
                        evidence=sentence,
                    ),
                )
            break

    return GraphDocumentArtifacts(nodes=list(nodes.values()), edges=list(edges.values()))


def _sentence_candidates(body: str) -> list[str]:
    stripped = body.replace("\r\n", "\n").replace("\r", "\n")
    parts = re.split(r"[\n。！？!?;；]", stripped)
    candidates: list[str] = []
    for part in parts:
        text = part.strip()
        if not text:
            continue
        fragments = [text]
        if sum(text.count(keyword) for keyword in ("依賴", "depends on", "影響", "affects")) > 1:
            fragments = [
                fragment.strip()
                for fragment in re.split(r"[，,]", text)
                if fragment.strip()
            ]
        candidates.extend(fragment for fragment in fragments if fragment)
    return candidates


def _clean_label(raw: str) -> str:
    cleaned = raw.strip()
    cleaned = re.sub(r"^[#*\-\d.\s]+", "", cleaned)
    cleaned = re.sub(r"^[A-Za-z][A-Za-z ]{0,30}:\s*", "", cleaned)
    cleaned = re.sub(r"^(?:因為|由於|because)\s+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = cleaned.strip(" ,:：()[]{}\"'。；;")
    return cleaned


def _split_targets(raw: str) -> list[str]:
    value = raw.strip()
    if not value:
        return []
    parts = re.split(r"\s*(?:與|和|及|、| and |,)\s*", value, flags=re.IGNORECASE)
    return [part for part in parts if part]


def _infer_entity_type(label: str, *, default: EntityType) -> EntityType:
    lowered = label.lower()
    if re.fullmatch(r"[A-Z][a-z]+(?: [A-Z][a-z]+)+", label):
        return "Person"
    if any(keyword in label for keyword in ("專案", "Atlas", "Borealis")):
        return "Project"
    if "project " in lowered and "service" not in lowered:
        return "Project"
    if any(keyword in label for keyword in ("延遲", "風險", "里程碑", "事故", "事件")):
        return "Event"
    if any(keyword in lowered for keyword in ("delay", "risk", "milestone", "incident", "event")):
        return "Event"
    if any(keyword in lowered for keyword in ("spec", "document", "analysis", "summary", "report")):
        return "Document"
    return default


def _register_node(
    nodes: dict[str, GraphNode],
    *,
    label: str,
    entity_type: EntityType,
    relpath: str,
    wiki_slug: str | None = None,
) -> GraphNode:
    node = GraphNode(
        id=make_node_id(entity_type, label),
        type=entity_type,
        label=label,
        aliases=[label],
        source_relpaths=[relpath],
        wiki_slugs=[wiki_slug] if wiki_slug else [],
    )
    existing = nodes.get(node.id)
    if existing is None:
        nodes[node.id] = node
        return node
    existing.aliases = sorted(set(existing.aliases) | {label})
    existing.source_relpaths = sorted(set(existing.source_relpaths) | {relpath})
    if wiki_slug:
        existing.wiki_slugs = sorted(set(existing.wiki_slugs) | {wiki_slug})
    return existing
