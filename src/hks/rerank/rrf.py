"""Deterministic reciprocal-rank-fusion reranker."""

from __future__ import annotations

from hks.retrieval.models import Candidate


def rrf_rerank(candidates: list[Candidate], *, k: int = 60) -> list[Candidate]:
    if not candidates:
        return []

    source_groups: dict[str, list[tuple[int, Candidate]]] = {}
    for index, candidate in enumerate(candidates):
        source_groups.setdefault(candidate.source_route, []).append((index, candidate))

    for route_candidates in source_groups.values():
        route_candidates.sort(key=lambda item: item[1].score, reverse=True)

    rrf_scores: dict[int, float] = {}
    for route_candidates in source_groups.values():
        for rank, (index, _candidate) in enumerate(route_candidates):
            rrf_scores[index] = rrf_scores.get(index, 0.0) + 1.0 / (k + rank + 1)

    ranked_indices = sorted(
        rrf_scores,
        key=lambda i: (rrf_scores[i], candidates[i].score),
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
