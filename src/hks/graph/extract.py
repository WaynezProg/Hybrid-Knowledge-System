"""Heuristic entity/relation extraction for Phase 2 graph updates."""

from __future__ import annotations

import hashlib
import re

from slugify import slugify

from hks.graph.store import (
    EntityType,
    GraphDocumentArtifacts,
    GraphEdge,
    GraphNode,
    RelationType,
    make_edge_id,
    make_node_id,
)
from hks.page_tree.model import PageTree, TreeNode

type RelationPattern = tuple[RelationType, str, bool]

_RELATION_PATTERNS: tuple[RelationPattern, ...] = (
    ("causes", r"(?P<left>.+?)(?:導致|造成|引發|使得?)(?P<right>.+)", False),
    ("causes", r"(?P<left>.+?)\s+causes?\s+(?P<right>.+)", False),
    (
        "contradicts",
        r"(?P<left>[^，,。；;!?！？]+?)(?:與|和)(?P<right>[^，,。；;!?！？]+?)(?:矛盾|衝突)",
        False,
    ),
    (
        "contradicts",
        r"(?:.*\b(?:however|but)\s+)?(?P<left>[^.，,;；]+?)\s+"
        r"(?:contradicts?|conflicts with)\s+(?P<right>[^.，,;；]+)",
        False,
    ),
    ("succeeds", r"(?P<left>.+?)\s+succeeds\s+(?P<right>.+)", False),
    ("succeeds", r"(?P<left>.+?)(?:之後)?(?:接續|接著|後續是)(?P<right>.+)", True),
    ("succeeds", r"(?P<left>.+?)\s+(?:followed by|is followed by)\s+(?P<right>.+)", True),
    ("succeeds", r"(?P<left>.+?)\s+precedes\s+(?P<right>.+)", True),
    ("impacts", r"(?P<left>.+?)(?:會|將|直接)?影響(?P<right>.+)", False),
    ("impacts", r"(?P<left>.+?)\s+affects?\s+(?P<right>.+)", False),
    ("depends_on", r"(?P<left>.+?)依賴(?P<right>.+)", False),
    ("depends_on", r"(?P<left>.+?)\s+depends on\s+(?P<right>.+)", False),
    ("references", r"(?P<left>.+?)(?:引用|參考)(?P<right>.+)", False),
    ("references", r"(?P<left>.+?)\s+references\s+(?P<right>.+)", False),
    ("belongs_to", r"(?P<left>.+?)(?:屬於|隸屬於)(?P<right>.+)", False),
    ("belongs_to", r"(?P<left>.+?)\s+belongs to\s+(?P<right>.+)", False),
    ("owns", r"(?P<left>.+?)(?:擁有|負責)(?P<right>.+)", False),
    ("owns", r"(?P<left>.+?)\s+owns\s+(?P<right>.+)", False),
)
_SENTENCE_BOUNDARY_RE = re.compile(
    r"[\n。！？!?;；]|(?<=[A-Za-z0-9]\.)\s+(?=[A-Z\u4e00-\u9fff])"
)
_ABBREVIATION_SUFFIXES = ("Dr.", "Mr.", "Ms.", "Mrs.", "Prof.", "Sr.", "Jr.", "St.", "U.S.", "U.K.")


def extract_document_graph(
    *,
    relpath: str,
    title: str,
    body: str,
    wiki_slug: str,
    page_tree: PageTree | None = None,
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

    if page_tree is not None:
        for tree_node in page_tree.flat_nodes():
            section_node = _register_section_node(
                nodes,
                tree_node=tree_node,
                label=tree_node.title,
                entity_type="Document",
                relpath=relpath,
            )
            if section_node.id != document_node.id:
                edge_id = make_edge_id(
                    relation="belongs_to",
                    source_id=section_node.id,
                    target_id=document_node.id,
                    source_relpath=relpath,
                )
                edges.setdefault(
                    edge_id,
                    GraphEdge(
                        id=edge_id,
                        relation="belongs_to",
                        source=section_node.id,
                        target=document_node.id,
                        source_relpath=relpath,
                        evidence=f"Section: {_section_path(page_tree, tree_node)}",
                    ),
                )
            for start, end in _non_child_ranges(tree_node, body_len=len(body)):
                _extract_relations(
                    nodes=nodes,
                    edges=edges,
                    relpath=relpath,
                    document_node=document_node,
                    body=body[start:end],
                    evidence_prefix=f"Section: {_section_path(page_tree, tree_node)} | ",
                    tree_title=tree_node.title,
                )
    else:
        _extract_relations(
            nodes=nodes,
            edges=edges,
            relpath=relpath,
            document_node=document_node,
            body=body,
            evidence_prefix=None,
            tree_title=None,
        )

    _apply_contextual_graph_heuristics(nodes, edges)
    return GraphDocumentArtifacts(nodes=list(nodes.values()), edges=list(edges.values()))


def _extract_relations(
    *,
    nodes: dict[str, GraphNode],
    edges: dict[str, GraphEdge],
    relpath: str,
    document_node: GraphNode,
    body: str,
    evidence_prefix: str | None,
    tree_title: str | None,
) -> None:
    for sentence in _sentence_candidates(body):
        evidence = f"{evidence_prefix}{sentence}" if evidence_prefix else sentence
        for relation, pattern, reverse in _RELATION_PATTERNS:
            match = re.search(pattern, sentence, flags=re.IGNORECASE)
            if match is None:
                continue
            source_label = _clean_label(match.group("left"))
            if not source_label:
                continue
            source_node = _register_node(
                nodes,
                label=source_label,
                entity_type=_infer_contextual_entity_type(
                    source_label,
                    default="Concept",
                    relation=relation,
                    role="target" if reverse else "source",
                    tree_title=tree_title,
                ),
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
                    evidence=evidence,
                ),
            )
            for target_label in _split_targets(match.group("right")):
                target = _clean_label(target_label)
                if not target:
                    continue
                target_node = _register_node(
                    nodes,
                    label=target,
                    entity_type=_infer_contextual_entity_type(
                        target,
                        default="Concept",
                        relation=relation,
                        role="source" if reverse else "target",
                        tree_title=tree_title,
                    ),
                    relpath=relpath,
                )
                edge_source = target_node if reverse else source_node
                edge_target = source_node if reverse else target_node
                edge_id = make_edge_id(
                    relation=relation,
                    source_id=edge_source.id,
                    target_id=edge_target.id,
                    source_relpath=relpath,
                )
                edges[edge_id] = GraphEdge(
                    id=edge_id,
                    relation=relation,
                    source=edge_source.id,
                    target=edge_target.id,
                    source_relpath=relpath,
                    evidence=evidence,
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
                        evidence=evidence,
                    ),
                )
            break


def _sentence_candidates(body: str) -> list[str]:
    stripped = body.replace("\r\n", "\n").replace("\r", "\n")
    parts = _sentence_parts(stripped)
    candidates: list[str] = []
    for part in parts:
        text = part.strip()
        if not text:
            continue
        fragments = [text]
        if (
            sum(
                text.count(keyword)
                for keyword in (
                    "依賴",
                    "depends on",
                    "影響",
                    "affects",
                    "導致",
                    "causes",
                    "矛盾",
                    "contradicts",
                    "接續",
                    "followed by",
                    "precedes",
                    "succeeds",
                )
            )
            > 1
        ):
            fragments = [
                fragment.strip()
                for fragment in re.split(r"[，,]", text)
                if fragment.strip()
            ]
        candidates.extend(fragment for fragment in fragments if fragment)
    return candidates


def _sentence_parts(text: str) -> list[str]:
    parts: list[str] = []
    start = 0
    for match in _SENTENCE_BOUNDARY_RE.finditer(text):
        if match.group().isspace() and _ends_with_abbreviation(text[: match.start()]):
            continue
        part = text[start : match.start()].strip()
        if part:
            parts.append(part)
        start = match.end()
    tail = text[start:].strip()
    if tail:
        parts.append(tail)
    return parts


def _ends_with_abbreviation(text: str) -> bool:
    stripped = text.rstrip()
    return any(stripped.endswith(suffix) for suffix in _ABBREVIATION_SUFFIXES)


def _clean_label(raw: str) -> str:
    cleaned = raw.strip()
    cleaned = re.sub(r"^[#*\-\d.\s]+", "", cleaned)
    cleaned = re.sub(r"^[A-Za-z][A-Za-z ]{0,30}:\s*", "", cleaned)
    cleaned = re.sub(r"^(?:因為|由於|because)\s+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^(?:但|但是|然而)\s*", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = cleaned.strip(" ,:：()[]{}\"'。；;.")
    return cleaned


def _split_targets(raw: str) -> list[str]:
    value = raw.strip()
    if not value:
        return []
    parts = re.split(r"\s*(?:與|和|及|、| and |,)\s*", value, flags=re.IGNORECASE)
    return [part for part in parts if part]


def _infer_contextual_entity_type(
    label: str,
    *,
    default: EntityType,
    relation: RelationType,
    role: str,
    tree_title: str | None,
) -> EntityType:
    if _label_matches_tree_title(label, tree_title):
        if _looks_like_document(label) or (
            tree_title is not None and _looks_like_document(tree_title)
        ):
            return "Document"
        return "Project"
    inferred = _infer_entity_type(label, default=default)
    if role == "source" and relation in ("causes", "impacts") and inferred == "Concept":
        return "Event"
    return inferred


def _label_matches_tree_title(label: str, tree_title: str | None) -> bool:
    if tree_title is None:
        return False
    lowered_label = label.lower()
    lowered_title = tree_title.lower()
    return lowered_label in lowered_title or lowered_title in lowered_label


def _looks_like_document(label: str) -> bool:
    lowered = label.lower()
    return any(
        keyword in lowered
        for keyword in ("spec", "document", "analysis", "summary", "report", "文件", "報告")
    )


def _infer_entity_type(label: str, *, default: EntityType) -> EntityType:
    lowered = label.lower()
    if any(keyword in label for keyword in ("專案", "Atlas", "Borealis")):
        return "Project"
    if "project " in lowered and "service" not in lowered:
        return "Project"
    if _looks_like_event(label):
        return "Event"
    if re.fullmatch(r"[A-Z][a-z]+(?: [A-Z][a-z]+)+", label):
        return "Person"
    if _looks_like_document(label):
        return "Document"
    return default


def _looks_like_event(label: str) -> bool:
    lowered = label.lower()
    if any(keyword in label for keyword in ("延遲", "風險", "里程碑", "事故", "事件")):
        return True
    return any(
        keyword in lowered
        for keyword in ("delay", "risk", "milestone", "incident", "event", "window")
    )


def _apply_contextual_graph_heuristics(
    nodes: dict[str, GraphNode],
    edges: dict[str, GraphEdge],
) -> None:
    depends_on_inbound: dict[str, set[str]] = {}
    for edge in edges.values():
        if edge.relation == "depends_on":
            depends_on_inbound.setdefault(edge.target, set()).add(edge.source)
    for target_id, source_ids in depends_on_inbound.items():
        if len(source_ids) > 1 and target_id in nodes and nodes[target_id].type != "Concept":
            _retag_node(nodes, edges, node_id=target_id, entity_type="Concept")


def _retag_node(
    nodes: dict[str, GraphNode],
    edges: dict[str, GraphEdge],
    *,
    node_id: str,
    entity_type: EntityType,
) -> None:
    old_node = nodes[node_id]
    new_id = make_node_id(entity_type, old_node.label)
    if new_id == node_id:
        return
    existing = nodes.get(new_id)
    if existing is None:
        nodes[new_id] = GraphNode(
            id=new_id,
            type=entity_type,
            label=old_node.label,
            aliases=old_node.aliases,
            source_relpaths=old_node.source_relpaths,
            wiki_slugs=old_node.wiki_slugs,
        )
    else:
        existing.aliases = sorted(set(existing.aliases) | set(old_node.aliases) | {old_node.label})
        existing.source_relpaths = sorted(
            set(existing.source_relpaths) | set(old_node.source_relpaths)
        )
        existing.wiki_slugs = sorted(set(existing.wiki_slugs) | set(old_node.wiki_slugs))
    nodes.pop(node_id, None)

    rebuilt_edges: dict[str, GraphEdge] = {}
    for edge in edges.values():
        source = new_id if edge.source == node_id else edge.source
        target = new_id if edge.target == node_id else edge.target
        edge_id = make_edge_id(
            relation=edge.relation,
            source_id=source,
            target_id=target,
            source_relpath=edge.source_relpath,
        )
        rebuilt_edges[edge_id] = GraphEdge(
            id=edge_id,
            relation=edge.relation,
            source=source,
            target=target,
            source_relpath=edge.source_relpath,
            evidence=edge.evidence,
        )
    edges.clear()
    edges.update(rebuilt_edges)


def _section_path(page_tree: PageTree, node: TreeNode) -> str:
    return page_tree.section_path(node.node_id) or node.title


def _non_child_ranges(node: TreeNode, *, body_len: int) -> list[tuple[int, int]]:
    start = _clamp_offset(node.start_offset, body_len)
    end = _clamp_offset(node.end_offset, body_len)
    if start >= end:
        return []

    ranges: list[tuple[int, int]] = []
    cursor = start
    for child in sorted(node.children, key=lambda item: item.start_offset):
        child_start = _clamp_offset(child.start_offset, body_len)
        child_end = _clamp_offset(child.end_offset, body_len)
        if child_end <= cursor or child_start >= end:
            continue
        if cursor < child_start:
            ranges.append((cursor, min(child_start, end)))
        cursor = max(cursor, min(child_end, end))
    if cursor < end:
        ranges.append((cursor, end))
    return ranges


def _clamp_offset(offset: int, body_len: int) -> int:
    return max(0, min(offset, body_len))


def _register_section_node(
    nodes: dict[str, GraphNode],
    *,
    tree_node: TreeNode,
    label: str,
    entity_type: EntityType,
    relpath: str,
) -> GraphNode:
    node = GraphNode(
        id=_section_node_id(
            entity_type=entity_type,
            relpath=relpath,
            tree_node=tree_node,
            label=label,
        ),
        type=entity_type,
        label=label,
        aliases=[label],
        source_relpaths=[relpath],
        wiki_slugs=[],
    )
    existing = nodes.get(node.id)
    if existing is None:
        nodes[node.id] = node
        return node
    existing.aliases = sorted(set(existing.aliases) | {label})
    existing.source_relpaths = sorted(set(existing.source_relpaths) | {relpath})
    return existing


def _section_node_id(
    *,
    entity_type: EntityType,
    relpath: str,
    tree_node: TreeNode,
    label: str,
) -> str:
    digest_source = f"{relpath}|{tree_node.node_id}"
    digest = hashlib.sha1(
        digest_source.encode("utf-8"),
        usedforsecurity=False,
    ).hexdigest()[:12]
    label_slug = slugify(label, separator="-").strip("-") or "section"
    return f"{entity_type.lower()}:section-{digest}-{label_slug}"


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
