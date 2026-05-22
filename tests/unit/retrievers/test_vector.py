"""Unit tests for vector candidate retrieval."""

from __future__ import annotations

from unittest.mock import MagicMock

from hks.retrievers.vector import (
    choose_vector_hit,
    collect_vector_candidates,
    lexical_terms,
    vector_hit_is_relevant,
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


def test_vector_hit_is_relevant_requires_lexical_overlap_when_query_has_terms() -> None:
    hit = SearchHit(
        chunk_id="c1",
        text="unrelated text",
        similarity=0.99,
        metadata={},
    )
    assert vector_hit_is_relevant("Owner Mia", hit) is False


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
    assert steps[0].kind == "vector_lookup"
