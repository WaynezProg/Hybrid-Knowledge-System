"""Graph query helpers for relation-oriented answers."""

from __future__ import annotations

import re
from dataclasses import dataclass

from hks.graph.store import GraphEdge, GraphPayload, GraphStore, RelationType

_ASCII_RE = re.compile(r"[a-z0-9]+")
_CJK_RUN_RE = re.compile(r"[\u4e00-\u9fff]+")
# How the question mentions a node, strongest first.
_FULL = 3  # a label or alias as written
_PHRASE = 2  # two words in a row of a label, or three CJK characters in a row
_WORD = 1  # one word of a label
# Below the graph route's auto write-back threshold: one shared word is not an identity.
_WORD_ONLY_CONFIDENCE = 0.7


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
    mentions = _mentions(question, payload)
    node_scores = _score_nodes(question, payload, mentions)
    edge_scores = _score_edges(question, payload, node_scores, desired_relations)

    # An edge answers the question only if it is of an asked relation and the question
    # names one of its ends; the relation word alone matches every edge of that kind.
    named = {
        edge_id: max(mentions.get(edge.source, 0), mentions.get(edge.target, 0))
        for edge_id, edge in payload.edges.items()
        if edge.relation in desired_relations
    }
    best = max(named.values(), default=0)
    if best == 0:
        return None
    # Every end named as clearly as the clearest one: two entities written in full are
    # both answered, and a word shared by chance does not ride along with either.
    ranked = sorted(
        (edge_id for edge_id, level in named.items() if level == best),
        key=lambda edge_id: edge_scores.get(edge_id, 0.0),
        reverse=True,
    )
    top_edges = [payload.edges[edge_id] for edge_id in ranked[:3]]

    answer = _render_answer(question, payload, top_edges)
    relpaths = sorted({edge.source_relpath for edge in top_edges})
    node_ids = sorted({edge.source for edge in top_edges} | {edge.target for edge in top_edges})
    relations = sorted({edge.relation for edge in top_edges})
    top_score = max(edge_scores.get(edge.id, 0.0) for edge in top_edges)
    confidence = min(0.99, 0.55 + (min(top_score, 6) * 0.06) + ((len(top_edges) - 1) * 0.05))
    if best == _WORD:
        confidence = min(confidence, _WORD_ONLY_CONFIDENCE)
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


def _cjk_bigrams(text: str) -> set[str]:
    """Overlapping pairs, so a word is found wherever the run around it starts."""
    pairs: set[str] = set()
    for run in _CJK_RUN_RE.findall(text):
        pairs.update(run[index : index + 2] for index in range(max(len(run) - 1, 1)))
    return pairs


def _terms(text: str) -> set[str]:
    lowered = text.lower()
    return {word for word in _ASCII_RE.findall(lowered) if len(word) >= 2} | _cjk_bigrams(lowered)


def _mention(question: str, alias: str) -> int:
    """How clearly ``question`` (lower case) names ``alias``."""
    name = alias.lower().strip()
    if not name:
        return 0
    # An ASCII end must fall on a word boundary: "ann" is not named by "planning".
    head = "(?<![a-z0-9])" if name[0].isascii() and name[0].isalnum() else ""
    tail = "(?![a-z0-9])" if name[-1].isascii() and name[-1].isalnum() else ""
    if re.search(head + re.escape(name) + tail, question):
        return _FULL
    asked, words = _ASCII_RE.findall(question), _ASCII_RE.findall(name)
    pairs = set(zip(asked, asked[1:], strict=False))
    if any(pair in pairs for pair in zip(words, words[1:], strict=False)):
        return _PHRASE
    cjk = {pair for pair in _cjk_bigrams(name) if len(pair) == 2}
    if len(cjk & _cjk_bigrams(question)) >= 2:
        return _PHRASE
    return _WORD if _terms(name) & _terms(question) else 0


def _mentions(question: str, payload: GraphPayload) -> dict[str, int]:
    lowered = question.lower()
    return {
        node_id: max((_mention(lowered, alias) for alias in {node.label, *node.aliases}), default=0)
        for node_id, node in payload.nodes.items()
    }


def _score_nodes(
    question: str, payload: GraphPayload, mentions: dict[str, int] | None = None
) -> dict[str, float]:
    query_terms = _terms(question)
    levels = mentions if mentions is not None else _mentions(question, payload)
    scores: dict[str, float] = {}
    for node_id, node in payload.nodes.items():
        aliases = {node.label, *node.aliases}
        alias_terms = set().union(*(_terms(alias) for alias in aliases if alias))
        # Written in full counts once, however many aliases the node has.
        bonus = 3.0 if levels.get(node_id, 0) == _FULL else 0.0
        scores[node_id] = float(len(query_terms & alias_terms)) + bonus
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
