"""Graph query helpers for relation-oriented answers."""

from __future__ import annotations

import re
from dataclasses import dataclass

from hks.graph.store import GraphEdge, GraphPayload, GraphStore, RelationType

_TOKEN_RE = re.compile(r"[a-z0-9]{2,}|[\u4e00-\u9fff]{1,2}", re.IGNORECASE)
# ``_score_nodes`` adds 3.0 when a label or alias appears in the question as written.
_NAMED_IN_FULL = 3.0
_PARTIAL_NAME_CONFIDENCE = 0.8


@dataclass(slots=True)
class GraphQueryResult:
    answer: str
    confidence: float
    relpaths: list[str]
    node_ids: list[str]
    edge_ids: list[str]
    relations: list[RelationType]


def answer_query(question: str, graph_store: GraphStore | None = None) -> GraphQueryResult | None:
    store = graph_store or GraphStore()
    payload = store.load()
    if not payload.edges:
        return None

    desired_relations = _desired_relations(question)
    if not desired_relations:
        return None
    node_scores = _score_nodes(question, payload)
    edge_scores = _score_edges(question, payload, node_scores, desired_relations)
    if not edge_scores:
        return None

    # An edge answers the question only if it is of an asked relation and the question
    # names one of its ends; the relation word alone matches every edge of that kind.
    named = {
        edge_id: max(
            node_scores.get(payload.edges[edge_id].source, 0.0),
            node_scores.get(payload.edges[edge_id].target, 0.0),
        )
        for edge_id in edge_scores
        if payload.edges[edge_id].relation in desired_relations
    }
    best_named = max(named.values(), default=0.0)
    if best_named <= 0:
        return None
    ranked = sorted(
        (edge_id for edge_id, score in named.items() if score >= best_named / 2),
        key=lambda edge_id: edge_scores[edge_id],
        reverse=True,
    )
    top_edges = [payload.edges[edge_id] for edge_id in ranked[:3]]

    answer = _render_answer(question, payload, top_edges)
    relpaths = sorted({edge.source_relpath for edge in top_edges})
    node_ids = sorted({edge.source for edge in top_edges} | {edge.target for edge in top_edges})
    relations = sorted({edge.relation for edge in top_edges})
    top_score = max(edge_scores[edge.id] for edge in top_edges)
    confidence = min(0.99, 0.55 + (min(top_score, 6) * 0.06) + ((len(top_edges) - 1) * 0.05))
    if best_named < _NAMED_IN_FULL:
        # Only some words of a label are in the question, not the label itself.
        confidence = min(confidence, _PARTIAL_NAME_CONFIDENCE)
    return GraphQueryResult(
        answer=answer,
        confidence=round(confidence, 4),
        relpaths=relpaths,
        node_ids=node_ids,
        edge_ids=[edge.id for edge in top_edges],
        relations=relations,
    )


def _desired_relations(question: str) -> set[RelationType]:
    lowered = question.lower()
    desired: set[RelationType] = set()
    if any(keyword in question for keyword in ("影響", "受影響", "波及")) or any(
        keyword in lowered for keyword in ("impact", "affect")
    ):
        desired.add("impacts")
    if any(keyword in question for keyword in ("導致", "造成", "引發", "原因")) or any(
        keyword in lowered for keyword in ("cause", "because", "reason")
    ):
        desired.add("causes")
    if any(keyword in question for keyword in ("矛盾", "衝突")) or any(
        keyword in lowered for keyword in ("contradict", "conflict")
    ):
        desired.add("contradicts")
    if any(keyword in question for keyword in ("接續", "後續", "接著")) or any(
        keyword in lowered for keyword in ("follow", "succeed")
    ):
        desired.add("succeeds")
    if any(keyword in question for keyword in ("依賴", "相依")) or any(
        keyword in lowered for keyword in ("depend", "dependency")
    ):
        desired.add("depends_on")
    if any(keyword in question for keyword in ("引用", "參考")) or "reference" in lowered:
        desired.add("references")
    if any(keyword in question for keyword in ("屬於", "隸屬")) or "belong" in lowered:
        desired.add("belongs_to")
    if any(keyword in question for keyword in ("擁有", "負責")) or "own" in lowered:
        desired.add("owns")
    return desired


def _terms(text: str) -> set[str]:
    return set(_TOKEN_RE.findall(text.lower()))


def _score_nodes(question: str, payload: GraphPayload) -> dict[str, float]:
    query_terms = _terms(question)
    lowered_question = question.lower()
    scores: dict[str, float] = {}
    for node_id, node in payload.nodes.items():
        aliases = {node.label, *node.aliases}
        alias_terms = set().union(*(_terms(alias) for alias in aliases if alias))
        overlap = len(query_terms & alias_terms)
        score = float(overlap)
        for alias in aliases:
            lowered_alias = alias.lower()
            if lowered_alias and lowered_alias in lowered_question:
                score += 3.0
        scores[node_id] = score
    return scores


def _score_edges(
    question: str,
    payload: GraphPayload,
    node_scores: dict[str, float],
    desired_relations: set[RelationType],
) -> dict[str, float]:
    query_terms = _terms(question)
    scores: dict[str, float] = {}
    for edge_id, edge in payload.edges.items():
        source_score = node_scores.get(edge.source, 0.0)
        target_score = node_scores.get(edge.target, 0.0)
        evidence_overlap = len(query_terms & _terms(edge.evidence))
        relation_bonus = 4.0 if edge.relation in desired_relations else 0.0
        score = relation_bonus + max(source_score, target_score) * 1.5 + evidence_overlap
        if score > 0:
            scores[edge_id] = score
    return scores


def _render_answer(question: str, payload: GraphPayload, edges: list[GraphEdge]) -> str:
    explain = any(keyword in question for keyword in ("為什麼", "原因")) or any(
        keyword in question.lower() for keyword in ("why", "because", "reason")
    )
    grouped: dict[tuple[str, RelationType], list[GraphEdge]] = {}
    for edge in edges:
        grouped.setdefault((edge.source, edge.relation), []).append(edge)

    sentences: list[str] = []
    for (source_id, relation), group in grouped.items():
        source_label = payload.nodes[source_id].label
        target_labels = [payload.nodes[edge.target].label for edge in group]
        targets = "、".join(dict.fromkeys(target_labels))
        sentence = _relation_sentence(source_label, relation, targets)
        if explain:
            evidence = group[0].evidence.strip()
            sentence = f"{sentence}（依據：{evidence[:100]}）"
        sentences.append(sentence)
    return "；".join(sentences)


def _relation_sentence(source_label: str, relation: RelationType, targets: str) -> str:
    if relation == "impacts":
        return f"{source_label} 會影響 {targets}"
    if relation == "depends_on":
        return f"{source_label} 依賴 {targets}"
    if relation == "references":
        return f"{source_label} 參考 {targets}"
    if relation == "belongs_to":
        return f"{source_label} 屬於 {targets}"
    if relation == "causes":
        return f"{source_label} 造成 {targets}"
    if relation == "contradicts":
        return f"{source_label} 與 {targets} 矛盾"
    if relation == "succeeds":
        return f"{source_label} 接續 {targets}"
    return f"{source_label} 擁有 {targets}"
