from unittest.mock import MagicMock

import pytest

from hks.rerank.rrf import rrf_rerank
from hks.retrieval.models import Candidate
from hks.retrievers.lexical import collect_lexical_candidates
from hks.storage.vector import SearchHit


def test_keyword_evidence_beats_a_semantic_neighbor_with_little_query_coverage() -> None:
    neighbor = Candidate(
        text="historical deployment completed",
        source_route="vector",
        score=0.8088,
        metadata={"query_coverage": 0.12},
    )
    rule = Candidate(
        text="raw review cannot replace final master ASR acceptance",
        source_route="lexical",
        score=0.6868,
        metadata={"query_coverage": 0.808},
    )

    assert rrf_rerank([neighbor, rule], question="raw final master ASR acceptance")[0].text == (
        rule.text
    )


def test_covered_vector_evidence_can_rise_within_its_own_route() -> None:
    candidates = [
        Candidate(
            text="deployment passed",
            source_route="vector",
            score=0.9,
            metadata={"query_coverage": 0.1},
        ),
        Candidate(
            text="fixture does not prove real integration",
            source_route="vector",
            score=0.7,
            metadata={"query_coverage": 0.95},
        ),
        Candidate(
            text="partial fixture match",
            source_route="lexical",
            score=0.75,
            metadata={"query_coverage": 0.8},
        ),
    ]

    ranked = rrf_rerank(candidates, question="fixture real integration")

    assert ranked[0].text == "fixture does not prove real integration"
    assert ranked[0].score == 0.7  # Ranking must not inflate retrieval confidence.
    assert len(ranked) == 3


def test_routes_without_measured_coverage_keep_their_original_score() -> None:
    graph = Candidate(text="relationship", source_route="graph", score=0.95, metadata={})
    lexical = Candidate(
        text="keyword match",
        source_route="lexical",
        score=0.68,
        metadata={"query_coverage": 0.8},
    )

    assert rrf_rerank([lexical, graph])[0] == graph


def test_lexical_route_supplies_comparable_coverage_to_the_reranker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HKS_HYBRID_SEARCH", "route")
    question = "raw 複核能代替 final master ASR 驗收嗎？"
    neighbor_text = "raw final export completed"
    rule_text = "raw 複核不能代替 final master ASR 驗收"
    store = MagicMock()
    store.count.return_value = 2
    store.all_chunks.return_value = [
        SearchHit("neighbor", neighbor_text, 0.65, {"source_relpath": "neighbor.md"}),
        SearchHit("rule", rule_text, 0.0, {"source_relpath": "rule.md"}),
    ]
    manifest = MagicMock()
    manifest.entries = {}
    neighbor = Candidate(
        text=neighbor_text,
        source_route="vector",
        score=0.89,
        metadata={"chunk_id": "neighbor", "_hks_match_text": neighbor_text},
    )

    lexical, _ = collect_lexical_candidates(
        question, vector_store=store, manifest=manifest, vector_candidates=[neighbor]
    )
    ranked = rrf_rerank([neighbor, *lexical], question=question)

    assert ranked[0].metadata["source_relpath"] == "rule.md"


def test_question_ranks_the_returned_passage_not_words_cut_off_from_its_chunk() -> None:
    question = "HTTP 422 roleKeys validation duplicate email guard"
    heading = Candidate(
        text="Software Studio HTTP API inventory",
        source_route="wiki",
        score=0.8,
        metadata={"query_coverage": 1.0},  # The full page matched, the answer did not.
    )
    rule = Candidate(
        text="HTTP 422 roleKeys validation does not prove the duplicate email guard",
        source_route="vector",
        score=0.7,
        metadata={"query_coverage": 0.5},
    )

    ranked = rrf_rerank([heading, rule], question=question)

    assert ranked[0].text == rule.text
    assert ranked[0].score == rule.score


def test_structured_daily_synthesis_is_not_displaced_by_a_clipped_date_heading() -> None:
    summary = Candidate(
        text="session2memory 修復、Paperclip 等待、Mogumogu 購物車",
        source_route="wiki",
        score=1.0,
        metadata={"session_memory_intent": True},
    )
    chunk = Candidate(
        text="# 2026-11-14 session2memory 修復",
        source_route="vector",
        score=0.9,
        metadata={},
    )

    assert rrf_rerank([summary, chunk], question="2026-11-14 做了什麼？")[0].text == summary.text
