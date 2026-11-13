"""Keyword (BM25) candidates as a route of their own (``HKS_HYBRID_SEARCH=route``, the default)."""

from __future__ import annotations

from hks.core.manifest import Manifest
from hks.core.schema import TraceStep
from hks.page_tree.store import TreeStore
from hks.retrieval.bm25 import bm25_rank, holds_identifiers, identifier_terms, query_coverage
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
    vector_candidates: list[Candidate] | None = None,
) -> tuple[list[Candidate], list[TraceStep]]:
    """Chunks ranked by BM25. The score is the share of the question's terms, weighted by
    rarity, that the chunk holds: comparable across questions, unlike a raw BM25 score.

    A chunk the vector route already nominated is not nominated a second time: that
    candidate keeps its route and its score, and only notes that the keywords agree. The
    lexical route therefore answers only with chunks the embedding did not bring up.
    """
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
    nominated = {
        candidate.metadata.get("chunk_id"): candidate for candidate in vector_candidates or []
    }
    shared = 0
    # A chunk that lacks an identifier the question names is about something else that
    # merely shares a word ("INC-00001" against a note on INC-90217).
    required = identifier_terms(question)
    missing_identifier = 0
    for rank, (index, bm25_score) in enumerate(matches, start=1):
        chunk = corpus[index]
        if not holds_identifiers(required, chunk.text):
            missing_identifier += 1
            continue
        already = nominated.get(chunk.chunk_id)
        if already is not None:
            already.metadata["lexical_rank"] = rank
            already.metadata["bm25_score"] = round(bm25_score, 4)
            shared += 1
            continue
        passage = best_vector_passage(question, chunk.text)
        score = round(_MAX_SCORE * query_coverage(question, chunk.text, texts), 4)
        metadata: dict[str, object] = dict(chunk.metadata)
        metadata["chunk_id"] = chunk.chunk_id
        metadata["_hks_match_text"] = chunk.text
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

    detail: dict[str, object] = {
        "hit": bool(candidates),
        "candidate_count": len(candidates),
        "shared_with_vector": shared,
    }
    if missing_identifier:
        detail["skipped_missing_identifier"] = missing_identifier
    if candidates:
        top = candidates[0]
        detail["final_score"] = top.score
        detail["bm25_score"] = top.metadata["bm25_score"]
        if isinstance(top.metadata.get("source_relpath"), str):
            detail["source_relpath"] = top.metadata["source_relpath"]
    return candidates, [TraceStep(kind="lexical_lookup", detail=detail)]
