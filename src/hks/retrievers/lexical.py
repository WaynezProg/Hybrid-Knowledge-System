"""Keyword (BM25) candidates as a route of their own (``HKS_HYBRID_SEARCH=route``)."""

from __future__ import annotations

from hks.core.manifest import Manifest
from hks.core.schema import TraceStep
from hks.page_tree.store import TreeStore
from hks.retrieval.bm25 import bm25_rank, query_coverage
from hks.retrieval.models import Candidate
from hks.retrievers.vector import (
    best_vector_passage,
    hybrid_max_chunks,
    hybrid_search_mode,
    vector_hit_lexical_score,
    vector_section_context,
)
from hks.storage.vector import VectorStore

_CANDIDATE_LIMIT = 5
_MAX_SCORE = 0.85


def collect_lexical_candidates(
    question: str,
    *,
    vector_store: VectorStore,
    manifest: Manifest,
) -> tuple[list[Candidate], list[TraceStep]]:
    """Chunks ranked by BM25. The score is the share of the question's terms, weighted by
    rarity, that the chunk holds: comparable across questions, unlike a raw BM25 score."""
    if hybrid_search_mode() != "route":
        return [], []
    if vector_store.count() > hybrid_max_chunks():
        return [], [
            TraceStep(
                kind="lexical_lookup",
                detail={"hit": False, "lexical_skipped": "chunk_count_above_limit"},
            )
        ]

    corpus = vector_store.all_chunks()
    texts = [chunk.text for chunk in corpus]
    matches = bm25_rank(question, texts, top_k=_CANDIDATE_LIMIT)
    tree_store = TreeStore(vector_store.paths)
    candidates: list[Candidate] = []
    for rank, (index, bm25_score) in enumerate(matches, start=1):
        chunk = corpus[index]
        passage = best_vector_passage(question, chunk.text)
        score = round(_MAX_SCORE * query_coverage(question, chunk.text, texts), 4)
        metadata: dict[str, object] = dict(chunk.metadata)
        metadata["lexical_overlap"] = vector_hit_lexical_score(question, chunk)
        metadata["lexical_rank"] = rank
        metadata["bm25_score"] = round(bm25_score, 4)
        metadata["final_score"] = score
        metadata.update(
            vector_section_context(
                chosen_hit=chunk, manifest=manifest, tree_store=tree_store, passage_text=passage
            )
        )
        candidates.append(
            Candidate(text=passage, source_route="lexical", score=score, metadata=metadata)
        )

    detail: dict[str, object] = {"hit": bool(candidates), "candidate_count": len(candidates)}
    if candidates:
        top = candidates[0]
        detail["final_score"] = top.score
        detail["bm25_score"] = top.metadata["bm25_score"]
        if isinstance(top.metadata.get("source_relpath"), str):
            detail["source_relpath"] = top.metadata["source_relpath"]
    return candidates, [TraceStep(kind="lexical_lookup", detail=detail)]
