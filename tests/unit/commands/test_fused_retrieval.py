"""Unit tests for fused retrieval pipeline."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from hks.commands.query import (
    Candidate,
    _candidate_evidence,
    _collect_graph_candidates,
    _collect_vector_candidates,
    _collect_wiki_candidates,
    _rerank_candidates,
    _rrf_rerank,
)
from hks.storage.vector import SearchHit


class TestCandidate:
    def test_candidate_fields(self) -> None:
        c = Candidate(
            text="answer text",
            source_route="wiki",
            score=0.9,
            metadata={"source_relpath": "doc.md"},
        )
        assert c.text == "answer text"
        assert c.source_route == "wiki"
        assert c.score == 0.9
        assert c.metadata["source_relpath"] == "doc.md"


class TestCollectWikiCandidates:
    def test_returns_candidate_on_hit(self) -> None:
        wiki_store = MagicMock()
        page = MagicMock()
        page.title = "Atlas"
        page.summary = "Atlas project summary"
        page.source_relpath = "atlas.md"
        page.slug = "atlas"
        wiki_store.search.return_value = page

        candidates, steps = _collect_wiki_candidates("Atlas 摘要", wiki_store=wiki_store)

        assert len(candidates) == 1
        assert candidates[0].source_route == "wiki"
        assert "Atlas" in candidates[0].text
        assert candidates[0].metadata["source_relpath"] == "atlas.md"

    def test_returns_empty_on_miss(self) -> None:
        wiki_store = MagicMock()
        wiki_store.search.return_value = None
        wiki_store.overview.return_value = None

        candidates, steps = _collect_wiki_candidates("random question", wiki_store=wiki_store)

        assert len(candidates) == 0


class TestCollectGraphCandidates:
    def test_returns_candidate_on_hit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        graph_store = MagicMock()
        mock_result = MagicMock()
        mock_result.answer = "A impacts B"
        mock_result.confidence = 0.88
        mock_result.relpaths = ["dep.md"]
        mock_result.node_ids = ["n1", "n2"]
        mock_result.edge_ids = ["e1"]
        mock_result.relations = ["impacts"]

        monkeypatch.setattr("hks.commands.query.answer_query", lambda q, gs: mock_result)

        candidates, steps = _collect_graph_candidates(
            "impact analysis", graph_store=graph_store
        )

        assert len(candidates) == 1
        assert candidates[0].source_route == "graph"

    def test_returns_empty_on_miss(self, monkeypatch: pytest.MonkeyPatch) -> None:
        graph_store = MagicMock()
        monkeypatch.setattr("hks.commands.query.answer_query", lambda q, gs: None)

        candidates, steps = _collect_graph_candidates("no match", graph_store=graph_store)

        assert len(candidates) == 0


class TestCollectVectorCandidates:
    def test_returns_candidates_for_relevant_hits(self) -> None:
        vector_store = MagicMock()
        vector_store.count.return_value = 10
        vector_store.search.return_value = [
            SearchHit(
                chunk_id="c1",
                text="matching text alpha",
                similarity=0.85,
                metadata={"source_relpath": "a.md"},
            ),
            SearchHit(
                chunk_id="c2",
                text="matching text beta",
                similarity=0.72,
                metadata={"source_relpath": "b.md"},
            ),
        ]
        vector_store.paths = MagicMock()

        manifest = MagicMock()
        manifest.entries = {}

        candidates, steps = _collect_vector_candidates(
            "matching text",
            vector_store=vector_store,
            manifest=manifest,
        )

        assert len(candidates) >= 1
        assert all(c.source_route == "vector" for c in candidates)

    def test_returns_empty_on_no_relevant_hits(self) -> None:
        vector_store = MagicMock()
        vector_store.count.return_value = 10
        vector_store.search.return_value = [
            SearchHit(
                chunk_id="c1",
                text="zzzzz",
                similarity=0.05,
                metadata={"source_relpath": "z.md"},
            ),
        ]
        vector_store.paths = MagicMock()

        manifest = MagicMock()
        manifest.entries = {}

        candidates, steps = _collect_vector_candidates(
            "totally unrelated query",
            vector_store=vector_store,
            manifest=manifest,
        )

        assert len(candidates) == 0


class TestRRFRerank:
    def test_ranks_by_reciprocal_fusion(self) -> None:
        candidates = [
            Candidate(text="wiki hit", source_route="wiki", score=1.0, metadata={}),
            Candidate(text="vector hit", source_route="vector", score=0.9, metadata={}),
            Candidate(text="graph hit", source_route="graph", score=0.7, metadata={}),
        ]

        ranked = _rrf_rerank(candidates)

        assert len(ranked) == 3
        assert ranked[0].score >= ranked[1].score >= ranked[2].score

    def test_empty_candidates(self) -> None:
        assert _rrf_rerank([]) == []

    def test_single_candidate(self) -> None:
        candidates = [
            Candidate(text="only one", source_route="wiki", score=1.0, metadata={}),
        ]

        ranked = _rrf_rerank(candidates)

        assert len(ranked) == 1
        assert ranked[0].text == "only one"

    def test_preserves_equal_duplicate_candidates(self) -> None:
        candidates = [
            Candidate(text="same", source_route="vector", score=0.8, metadata={}),
            Candidate(text="same", source_route="vector", score=0.8, metadata={}),
        ]

        ranked = _rrf_rerank(candidates)

        assert len(ranked) == 2


class TestRerankCandidates:
    def test_uses_rrf_when_no_api_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("HKS_LLM_PROVIDER_OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        candidates = [
            Candidate(text="a", source_route="wiki", score=1.0, metadata={}),
            Candidate(text="b", source_route="vector", score=0.5, metadata={}),
        ]

        ranked, strategy = _rerank_candidates("question", candidates)

        assert strategy == "rrf"
        assert len(ranked) == 2

    def test_uses_rrf_when_api_key_set_without_network_opt_in(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("HKS_LLM_PROVIDER_OPENAI_API_KEY", "sk-test")
        monkeypatch.delenv("HKS_LLM_NETWORK_OPT_IN", raising=False)

        def fail_llm_rerank(*_args: object, **_kwargs: object) -> list[Candidate]:
            raise AssertionError("LLM rerank must require HKS_LLM_NETWORK_OPT_IN=1")

        monkeypatch.setattr("hks.commands.query._llm_rerank", fail_llm_rerank)

        candidates = [
            Candidate(text="a", source_route="wiki", score=1.0, metadata={}),
            Candidate(text="b", source_route="vector", score=0.5, metadata={}),
        ]

        ranked, strategy = _rerank_candidates("question", candidates)

        assert strategy == "rrf"
        assert [candidate.text for candidate in ranked] == ["a", "b"]


class TestCandidateEvidence:
    def test_vector_candidate_evidence_includes_winning_quote_and_location(self) -> None:
        candidate = Candidate(
            text="clause 7.4 requires risk controls before launch.",
            source_route="vector",
            score=0.91,
            metadata={
                "source_relpath": "reports/launch-plan.md",
                "section_path": "Launch Plan > Risk Controls",
                "page_range": {"start": 4, "end": 6},
            },
        )

        assert _candidate_evidence(candidate) == [
            {
                "source_relpath": "reports/launch-plan.md",
                "route": "vector",
                "section_path": "Launch Plan > Risk Controls",
                "page_range": {"start": 4, "end": 6},
                "quote": "clause 7.4 requires risk controls before launch.",
            }
        ]

    def test_graph_candidate_evidence_uses_edge_quotes_per_relpath(self) -> None:
        candidate = Candidate(
            text="Atlas 會影響 Billing API",
            source_route="graph",
            score=0.88,
            metadata={
                "relpaths": ["dependency-map.md"],
                "evidence_by_relpath": {
                    "dependency-map.md": "Project Atlas affects Billing API."
                },
            },
        )

        assert _candidate_evidence(candidate) == [
            {
                "source_relpath": "dependency-map.md",
                "route": "graph",
                "quote": "Project Atlas affects Billing API.",
            }
        ]
