"""Vector candidate retrieval."""

from __future__ import annotations

import re

from hks.core.manifest import Manifest
from hks.core.schema import TraceStep
from hks.core.text_models import simple_tokenize
from hks.page_tree.model import PageTree, TreeNode
from hks.page_tree.store import TreeStore
from hks.retrieval.evidence import evidence_quote
from hks.retrieval.models import Candidate
from hks.storage.vector import SearchHit, VectorStore

_LEXICAL_SCORE_BONUS = 0.08
_MAX_LEXICAL_SCORE_BONUS = 0.24
_PASSAGE_MAX_TOKENS = 96
_PASSAGE_SPLIT_RE = re.compile(r"(?<!\d\.)(?<=[.!?。！？])\s*")


def lexical_terms(text: str) -> set[str]:
    lowered = text.lower()
    terms = set(re.findall(r"[a-z0-9]{2,}", lowered))
    for chunk in re.findall(r"[\u4e00-\u9fff]{2,}", text):
        if len(chunk) == 2:
            terms.add(chunk)
            continue
        terms.update(chunk[index : index + 2] for index in range(len(chunk) - 1))
    return terms


def vector_hit_is_relevant(question: str, hit: SearchHit) -> bool:
    return hit.similarity >= 0.0


def vector_hit_lexical_score(question: str, hit: SearchHit) -> int:
    query_terms = lexical_terms(question)
    text_terms = lexical_terms(hit.text)
    return len(query_terms & text_terms)


def vector_hit_final_score(question: str, hit: SearchHit) -> float:
    lexical_bonus = min(
        vector_hit_lexical_score(question, hit) * _LEXICAL_SCORE_BONUS,
        _MAX_LEXICAL_SCORE_BONUS,
    )
    return min(1.0, hit.similarity + lexical_bonus)


def best_vector_passage(
    question: str,
    text: str,
    *,
    max_tokens: int = _PASSAGE_MAX_TOKENS,
) -> str:
    passages = [passage.strip() for passage in _PASSAGE_SPLIT_RE.split(text) if passage.strip()]
    if not passages:
        return _trim_passage_tokens(text, max_tokens=max_tokens)

    query_terms = lexical_terms(question)
    best = max(
        passages,
        key=lambda passage: (
            len(query_terms & lexical_terms(passage)),
            -len(simple_tokenize(passage)),
        ),
    )
    if query_terms and not query_terms & lexical_terms(best):
        return _trim_passage_tokens(text, max_tokens=max_tokens)
    return _trim_passage_tokens(best, max_tokens=max_tokens)


def _trim_passage_tokens(text: str, *, max_tokens: int) -> str:
    tokens = simple_tokenize(text)
    if len(tokens) <= max_tokens:
        return text
    return " ".join(tokens[:max_tokens]).strip()


def choose_vector_hit(question: str, hits: list[SearchHit]) -> SearchHit | None:
    if not hits:
        return None
    return max(
        hits,
        key=lambda hit: (
            vector_hit_final_score(question, hit),
            vector_hit_lexical_score(question, hit),
            hit.similarity,
        ),
    )


def vector_trace_detail(
    *,
    question: str,
    top_k: int,
    top_similarity: float,
    chosen_hit: SearchHit | None,
    manifest: Manifest | None = None,
    tree_store: TreeStore | None = None,
) -> dict[str, object]:
    detail: dict[str, object] = {
        "top_k": top_k,
        "top_similarity": round(top_similarity, 4),
    }
    if chosen_hit is None:
        return detail
    passage_text = best_vector_passage(question, chosen_hit.text)
    detail["quote"] = evidence_quote(passage_text)
    detail["lexical_overlap"] = vector_hit_lexical_score(question, chosen_hit)
    detail["vector_similarity"] = round(chosen_hit.similarity, 4)
    detail["final_score"] = round(vector_hit_final_score(question, chosen_hit), 4)
    for key in (
        "source_relpath",
        "sheet_name",
        "slide_index",
        "section_type",
        "row_index",
        "source_format",
        "ocr_confidence",
        "source_engine",
        "hks_type",
        "date",
        "source_domain",
        "generator",
        "workspace_id",
        "memory_kind",
        "tool",
        "session_id",
        "evidence_id",
    ):
        if key in chosen_hit.metadata:
            detail[key] = chosen_hit.metadata[key]
    if manifest is not None and tree_store is not None:
        detail.update(
            vector_section_context(
                chosen_hit=chosen_hit,
                manifest=manifest,
                tree_store=tree_store,
                passage_text=passage_text,
            )
        )
    return detail


def vector_section_context(
    *,
    chosen_hit: SearchHit,
    manifest: Manifest,
    tree_store: TreeStore,
    passage_text: str | None = None,
) -> dict[str, object]:
    relpath = chosen_hit.metadata.get("source_relpath")
    node_id = chosen_hit.metadata.get("tree_node_id")
    if not isinstance(relpath, str) or not isinstance(node_id, str):
        return {}

    entry = manifest.entries.get(relpath)
    if entry is None:
        return {}
    tree_slug = entry.derived.page_tree
    if tree_slug is None:
        return {}

    try:
        tree = tree_store.load(tree_slug)
    except Exception:
        return {}
    if tree.source_relpath != relpath or tree.source_sha256 != entry.sha256:
        return {}

    node = _node_for_passage(tree, passage_text) or next(
        (candidate for candidate in tree.flat_nodes() if candidate.node_id == node_id),
        None,
    )
    section_path = tree.section_path(node.node_id) if node is not None else None
    if section_path is None or node is None:
        return {}

    context: dict[str, object] = {"section_path": section_path}
    page_start = node.metadata.get("page_start")
    page_end = node.metadata.get("page_end")
    if isinstance(page_start, int) and isinstance(page_end, int):
        context["page_range"] = {"start": page_start, "end": page_end}
    return context


def _node_for_passage(tree: PageTree, passage_text: str | None) -> TreeNode | None:
    if not passage_text:
        return None
    lowered = passage_text.casefold()
    matches = [
        node
        for node in tree.flat_nodes()
        if node.title and node.title.casefold() in lowered
    ]
    if not matches:
        return None
    return max(matches, key=lambda node: (node.level, len(node.title)))


def collect_vector_candidates(
    question: str,
    *,
    vector_store: VectorStore,
    manifest: Manifest,
) -> tuple[list[Candidate], list[TraceStep]]:
    steps: list[TraceStep] = []
    candidates: list[Candidate] = []

    candidate_limit = max(5, min(50, vector_store.count()))
    hits = vector_store.search(question, top_k=candidate_limit)
    top_similarity = hits[0].similarity if hits else 0.0

    tree_store = TreeStore(vector_store.paths)

    for hit in hits[:5]:
        passage_text = best_vector_passage(question, hit.text)
        metadata: dict[str, object] = dict(hit.metadata)
        metadata["lexical_overlap"] = vector_hit_lexical_score(question, hit)
        metadata["vector_similarity"] = hit.similarity
        metadata["final_score"] = vector_hit_final_score(question, hit)
        section_ctx = vector_section_context(
            chosen_hit=hit,
            manifest=manifest,
            tree_store=tree_store,
            passage_text=passage_text,
        )
        metadata.update(section_ctx)
        candidates.append(
            Candidate(
                text=passage_text,
                source_route="vector",
                score=vector_hit_final_score(question, hit),
                metadata=metadata,
            )
        )

    detail = vector_trace_detail(
        question=question,
        top_k=candidate_limit,
        top_similarity=top_similarity,
        chosen_hit=choose_vector_hit(question, hits),
        manifest=manifest,
        tree_store=tree_store,
    )
    steps.append(TraceStep(kind="vector_lookup", detail=detail))

    return candidates, steps
