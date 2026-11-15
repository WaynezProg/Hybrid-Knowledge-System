"""Deterministic reciprocal-rank-fusion reranker."""

from __future__ import annotations

import math

from hks.retrieval.bm25 import CoverageScorer
from hks.retrieval.models import Candidate


def _evidence_score(candidate: Candidate, coverage: object) -> float:
    if (
        isinstance(coverage, int | float)
        and not isinstance(coverage, bool)
        and math.isfinite(coverage)
        and 0.0 <= coverage <= 1.0
    ):
        return candidate.score * (0.25 + 0.75 * float(coverage))
    return candidate.score


def rrf_rerank(
    candidates: list[Candidate], *, k: int = 60, question: str | None = None
) -> list[Candidate]:
    if not candidates:
        return []

    # Compare the actual answer snippets, rather than a whole chunk whose matching
    # words may have been trimmed away. Preserve raw scores for confidence gates.
    # A structured daily answer has already been filtered by date and subject and
    # may synthesize several entries. A clipped chunk repeating the date must not
    # displace that complete answer merely by repeating the question's wording.
    structured = any(item.metadata.get("session_memory_intent") for item in candidates)
    scorer = (
        CoverageScorer(question, [item.text for item in candidates])
        if question and not structured
        else None
    )
    evidence_scores = {
        index: _evidence_score(
            candidate,
            scorer.score(candidate.text)
            if scorer is not None and scorer.measurable
            else None,
        )
        for index, candidate in enumerate(candidates)
    }
    source_groups: dict[str, list[tuple[int, Candidate]]] = {}
    for index, candidate in enumerate(candidates):
        source_groups.setdefault(candidate.source_route, []).append((index, candidate))

    for route_candidates in source_groups.values():
        route_candidates.sort(
            key=lambda item: (evidence_scores[item[0]], item[1].score), reverse=True
        )

    rrf_scores: dict[int, float] = {}
    for route_candidates in source_groups.values():
        for rank, (index, _candidate) in enumerate(route_candidates):
            rrf_scores[index] = rrf_scores.get(index, 0.0) + 1.0 / (k + rank + 1)

    ranked_indices = sorted(
        rrf_scores,
        key=lambda i: (rrf_scores[i], evidence_scores[i], candidates[i].score),
        reverse=True,
    )
    return [
        Candidate(
            text=candidates[i].text,
            source_route=candidates[i].source_route,
            score=candidates[i].score,
            metadata=candidates[i].metadata,
        )
        for i in ranked_indices
    ]
