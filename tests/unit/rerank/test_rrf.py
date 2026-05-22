"""Unit tests for deterministic RRF reranker."""

from __future__ import annotations

from hks.rerank.rrf import rrf_rerank
from hks.retrieval.models import Candidate


def test_rrf_ranks_by_reciprocal_fusion() -> None:
    candidates = [
        Candidate(text="wiki hit", source_route="wiki", score=1.0, metadata={}),
        Candidate(text="vector hit", source_route="vector", score=0.9, metadata={}),
        Candidate(text="graph hit", source_route="graph", score=0.7, metadata={}),
    ]

    ranked = rrf_rerank(candidates)

    assert len(ranked) == 3
    assert ranked[0].score >= ranked[1].score >= ranked[2].score


def test_rrf_empty_candidates() -> None:
    assert rrf_rerank([]) == []


def test_rrf_preserves_equal_duplicate_candidates() -> None:
    candidates = [
        Candidate(text="same", source_route="vector", score=0.8, metadata={}),
        Candidate(text="same", source_route="vector", score=0.8, metadata={}),
    ]

    assert len(rrf_rerank(candidates)) == 2
