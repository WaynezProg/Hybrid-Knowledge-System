"""Unit tests for vector candidate retrieval."""

from __future__ import annotations

from unittest.mock import MagicMock

from hks.retrieval.bm25 import bm25_rank, lexical_tokens
from hks.retrievers.vector import (
    choose_vector_hit,
    collect_vector_candidates,
    lexical_terms,
)
from hks.storage.vector import SearchHit


def test_lexical_terms_extracts_english_and_chinese_bigrams() -> None:
    assert "atlas" in lexical_terms("Atlas risk")
    assert "風險" in lexical_terms("風險評估")


def test_vector_hit_selection_prefers_more_lexical_matches_over_similarity_noise() -> None:
    broad_hit = SearchHit(
        chunk_id="png:0",
        text="Owner Iris appears in the PNG image.",
        similarity=0.99,
        metadata={"source_format": "png"},
    )
    precise_hit = SearchHit(
        chunk_id="jpg:0",
        text="Owner Mia appears in the JPG image.",
        similarity=0.91,
        metadata={"source_format": "jpg"},
    )

    assert choose_vector_hit("detail Owner Mia", [broad_hit, precise_hit]) == precise_hit


def test_vector_hit_selection_keeps_vector_hit_without_lexical_overlap() -> None:
    hit = SearchHit(
        chunk_id="c1",
        text="unrelated text",
        similarity=0.99,
        metadata={},
    )
    assert choose_vector_hit("Owner Mia", [hit]) == hit


def test_collect_vector_returns_candidates_for_relevant_hits() -> None:
    vector_store = MagicMock()
    vector_store.count.return_value = 10
    vector_store.search.return_value = [
        SearchHit(
            chunk_id="c1",
            text="matching text alpha",
            similarity=0.85,
            metadata={"source_relpath": "a.md"},
        )
    ]
    vector_store.all_chunks.return_value = []
    vector_store.paths = MagicMock()
    manifest = MagicMock()
    manifest.entries = {}

    candidates, steps = collect_vector_candidates(
        "matching text",
        vector_store=vector_store,
        manifest=manifest,
    )

    assert len(candidates) == 1
    assert candidates[0].source_route == "vector"
    assert candidates[0].metadata["lexical_overlap"] == 2
    assert candidates[0].metadata["vector_similarity"] == 0.85
    assert candidates[0].metadata["final_score"] == 1.0
    assert candidates[0].score == 1.0
    assert steps[0].kind == "vector_lookup"


def test_collect_vector_keeps_hits_without_lexical_overlap() -> None:
    vector_store = MagicMock()
    vector_store.count.return_value = 10
    vector_store.search.return_value = [
        SearchHit(
            chunk_id="c1",
            text="unrelated text",
            similarity=0.91,
            metadata={"source_relpath": "a.md"},
        )
    ]
    vector_store.all_chunks.return_value = []
    vector_store.paths = MagicMock()
    manifest = MagicMock()
    manifest.entries = {}

    candidates, steps = collect_vector_candidates(
        "Owner Mia",
        vector_store=vector_store,
        manifest=manifest,
    )

    assert len(candidates) == 1
    assert candidates[0].metadata["lexical_overlap"] == 0
    assert candidates[0].metadata["vector_similarity"] == 0.91
    assert candidates[0].metadata["final_score"] == 0.91
    assert candidates[0].score == 0.91
    assert steps[0].detail["lexical_overlap"] == 0


def test_bm25_ranks_the_chunk_holding_the_rare_term_first() -> None:
    documents = [
        "deployment notes for the atlas service",
        "error ERR-4012 happens when the atlas token expires",
        "風險評估與時程",
    ]

    assert [index for index, _ in bm25_rank("ERR-4012 atlas", documents, top_k=5)] == [1, 0]
    assert [index for index, _ in bm25_rank("風險評估", documents, top_k=5)] == [2]
    assert bm25_rank("nothing here", documents, top_k=5) == []
    assert lexical_tokens("風險評估 x ok ok") == ["ok", "ok", "風險", "險評", "評估"]


def _hybrid_store(dense: list[SearchHit], corpus: list[SearchHit]) -> MagicMock:
    vector_store = MagicMock()
    vector_store.count.return_value = len(corpus)
    vector_store.search.return_value = dense
    vector_store.all_chunks.return_value = corpus
    vector_store.similarities.return_value = {"exact": 0.31}
    vector_store.paths = MagicMock()
    return vector_store


def _chunk(chunk_id: str, text: str, similarity: float = 0.0) -> SearchHit:
    return SearchHit(
        chunk_id=chunk_id, text=text, similarity=similarity, metadata={"source_relpath": "a.md"}
    )


def test_hybrid_adds_a_keyword_match_the_embedding_missed(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("HKS_HYBRID_SEARCH", "fused")
    dense = [
        _chunk(f"d{index}", f"general remarks {index}", 0.6 - index / 100) for index in range(6)
    ]
    exact = _chunk("exact", "ticket ERR-4012 is fixed by rotating the token")
    vector_store = _hybrid_store(dense, [*dense, exact])
    manifest = MagicMock()
    manifest.entries = {}

    candidates, steps = collect_vector_candidates(
        "ERR-4012", vector_store=vector_store, manifest=manifest
    )

    assert len(candidates) == 5
    found = next(c for c in candidates if "ERR-4012" in c.text)
    assert found.metadata["lexical_rank"] == 1 and "dense_rank" not in found.metadata
    assert found.metadata["vector_similarity"] == 0.31
    assert found.score == 0.31 + 2 * 0.08, "similarity plus overlap bonus, as for dense hits"
    assert steps[0].detail["retrieval_mode"] == "hybrid"
    assert steps[0].detail["lexical_only_count"] == 1
    vector_store.similarities.assert_called_once_with("ERR-4012", ["exact"])


def test_hybrid_puts_a_chunk_found_both_ways_first(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("HKS_HYBRID_SEARCH", "fused")
    dense = [_chunk("d0", "general remarks", 0.62), _chunk("both", "atlas rollout plan", 0.6)]
    vector_store = _hybrid_store(dense, list(dense))
    manifest = MagicMock()
    manifest.entries = {}

    candidates, _ = collect_vector_candidates(
        "atlas rollout", vector_store=vector_store, manifest=manifest
    )

    assert [c.text for c in candidates] == ["atlas rollout plan", "general remarks"]
    assert candidates[0].metadata["dense_rank"] == 2 and candidates[0].metadata["lexical_rank"] == 1


def test_hybrid_can_be_switched_off_and_skips_a_large_store(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    dense = [_chunk("d0", "general remarks", 0.6)]
    corpus = [*dense, _chunk("exact", "ERR-4012 details")]
    manifest = MagicMock()
    manifest.entries = {}

    monkeypatch.setenv("HKS_HYBRID_SEARCH", "0")
    off = _hybrid_store(dense, corpus)
    candidates, steps = collect_vector_candidates("ERR-4012", vector_store=off, manifest=manifest)
    assert len(candidates) == 1 and steps[0].detail["retrieval_mode"] == "dense"
    off.all_chunks.assert_not_called()

    monkeypatch.setenv("HKS_HYBRID_SEARCH", "fused")
    monkeypatch.setenv("HKS_HYBRID_MAX_CHUNKS", "1")
    large = _hybrid_store(dense, corpus)
    _, steps = collect_vector_candidates("ERR-4012", vector_store=large, manifest=manifest)
    assert steps[0].detail["lexical_skipped"] == "chunk_count_above_limit"
    large.all_chunks.assert_not_called()
