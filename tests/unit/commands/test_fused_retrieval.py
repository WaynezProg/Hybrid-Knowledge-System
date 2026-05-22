"""Command-level smoke tests for query orchestration."""

from __future__ import annotations

from hks.commands.query import _build_no_hit_response, _passes_final_score_gate
from hks.retrieval.models import Candidate


def test_build_no_hit_response_keeps_public_shape() -> None:
    response = _build_no_hit_response("wiki", [])

    assert response.answer == "未能於現有知識中找到答案"
    assert response.source == []
    assert response.confidence == 0.0
    assert response.trace.route == "wiki"


def test_vector_final_score_gate_rejects_low_similarity_hit() -> None:
    candidate = Candidate(
        text="irrelevant",
        source_route="vector",
        score=0.24,
        metadata={"lexical_overlap": 0},
    )

    assert not _passes_final_score_gate(candidate)


def test_vector_final_score_gate_keeps_strong_hit_without_lexical_overlap() -> None:
    candidate = Candidate(
        text="semantic match",
        source_route="vector",
        score=0.91,
        metadata={"lexical_overlap": 0},
    )

    assert _passes_final_score_gate(candidate)


def test_vector_final_score_gate_keeps_lexical_hit_at_lower_score() -> None:
    candidate = Candidate(
        text="lexical match",
        source_route="vector",
        score=0.21,
        metadata={"lexical_overlap": 2},
    )

    assert _passes_final_score_gate(candidate)
