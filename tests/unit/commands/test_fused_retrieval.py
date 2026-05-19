"""Unit tests for fused retrieval pipeline."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from hks.commands.query import Candidate, _collect_wiki_candidates, _collect_graph_candidates, _collect_vector_candidates
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
            SearchHit(chunk_id="c1", text="matching text alpha", similarity=0.85, metadata={"source_relpath": "a.md"}),
            SearchHit(chunk_id="c2", text="matching text beta", similarity=0.72, metadata={"source_relpath": "b.md"}),
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
            SearchHit(chunk_id="c1", text="zzzzz", similarity=0.05, metadata={"source_relpath": "z.md"}),
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
